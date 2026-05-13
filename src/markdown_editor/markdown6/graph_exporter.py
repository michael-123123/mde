"""Document-graph exporter: shared DOT generation + rendering.

Architecture: one concrete :class:`GraphExporter` parameterised over a
:class:`GraphExporterConfig` (abstract). GUI and CLI provide their own config
subclasses - the GUI one reads from Qt widgets, the CLI one from an argparse
``Namespace``. The exporter itself contains all the logic and is Qt-free, so
``mde graph`` / ``mde validate`` don't pay the cost of importing PySide6.

All config access happens through abstract properties; subclasses decide
whether values are read live (e.g. on each property access against a widget)
or frozen at construction (e.g. from a parsed ``args`` Namespace).
"""

import errno
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal

from markdown_editor.markdown6 import graphviz_service
from markdown_editor.markdown6.link_detection import (
    MD_LINK_PATTERN,
    WIKI_LINK_PATTERN,
    mask_verbatim_regions,
)
from markdown_editor.markdown6.logger import getLogger

logger = getLogger(__name__)

BrokenHandling = Literal["red", "exclude", "warning", "normal"]
OutputFormat = Literal["svg", "png", "pdf", "dot"]


class GraphExporterConfig(ABC):
    """Read-only configuration surface for :class:`GraphExporter`.

    Subclasses implement the abstract properties. Values are read on each
    access, so a "live" subclass (Qt widgets) and a "frozen" subclass
    (argparse Namespace) both fit without adapter plumbing.
    """

    @property
    @abstractmethod
    def project_path(self) -> Path: ...

    @property
    @abstractmethod
    def selected_files(self) -> list[Path]: ...

    @property
    @abstractmethod
    def is_directed(self) -> bool: ...

    @property
    @abstractmethod
    def engine(self) -> str: ...

    @property
    @abstractmethod
    def label_template(self) -> str: ...

    @property
    @abstractmethod
    def labels_below(self) -> bool: ...

    @property
    @abstractmethod
    def broken_handling(self) -> BrokenHandling: ...

    @property
    @abstractmethod
    def dark_mode(self) -> bool: ...

    @property
    @abstractmethod
    def output_format(self) -> OutputFormat: ...


class GraphExporter:
    """Builds a Graphviz document-link graph from a project's markdown files.

    The exporter is concrete; configuration is injected via the ``config``
    argument. See :class:`GraphExporterConfig` for the abstract surface.
    """

    def __init__(self, config: GraphExporterConfig):
        self._config = config

    @property
    def config(self) -> GraphExporterConfig:
        """The configuration this exporter reads from."""
        return self._config

    # ── File-index + link resolution ────────────────────────────────────

    def build_file_index(self) -> dict[str, Path]:
        """Index :attr:`config.selected_files` for wiki-link resolution.

        Each file is recorded both by its lowercase stem (so ``[[Note]]``
        finds ``note.md``) and by its project-relative path without the
        extension (so ``[[folder/Note]]`` finds ``folder/note.md``).
        """
        file_index: dict[str, Path] = {}
        for f in self._config.selected_files:
            file_index[f.stem.lower()] = f
            try:
                rel_path = f.relative_to(self._config.project_path)
            except ValueError:
                # File outside the project root; only stem-indexed.
                continue
            rel_no_ext = str(rel_path.with_suffix("")).lower()
            file_index[rel_no_ext] = f
        return file_index

    def resolve_link(
        self,
        target: str,
        source_file: Path,
        file_index: dict[str, Path],
        line_number: int | None = None,
    ) -> Path | None:
        """Resolve a wiki-link target to a file path.

        Tries, in order:
          1. Direct stem (or project-relative-no-ext) match in *file_index*.
          2. With ``.md`` appended.
          3. As a path relative to *source_file*'s directory, with ``.md``.

        Returns ``None`` if none match, or if step 3 raises
        ``OSError(ENAMETOOLONG)`` because the captured target is
        pathologically long (a malformed bare-prose multi-line ``[[...]]``
        that :func:`mask_verbatim_regions` couldn't strip). The
        ``ENAMETOOLONG`` case is logged at ``source_file:line_number`` so
        the user has a pointer to the broken link.
        """
        if target in file_index:
            return file_index[target]

        target_md = target + ".md"
        if target_md.lower() in file_index:
            return file_index[target_md.lower()]

        rel_path = source_file.parent / (target + ".md")
        try:
            if rel_path.exists():
                return rel_path.resolve()
        except OSError as e:
            if e.errno == errno.ENAMETOOLONG:
                loc = f"{source_file}:{line_number}" if line_number else str(source_file)
                logger.warning(
                    "Skipping wiki link at %s: target too long (%d chars)",
                    loc, len(target),
                )
                return None
            raise

        return None

    # ── DOT emission ────────────────────────────────────────────────────

    def _get_label(self, path: Path | str) -> str:
        """Render *path* through the configured label template."""
        if not isinstance(path, Path):
            return str(path)
        try:
            rel = path.relative_to(self._config.project_path)
        except ValueError:
            rel = path
        return self._config.label_template.format(
            stem=path.stem,
            filename=path.name,
            relative_path=str(rel),
            relative_path_no_ext=str(rel.with_suffix("")),
        )

    def _get_tooltip(self, path: Path | str) -> str:
        """Project-relative path as tooltip text (absolute fallback)."""
        if not isinstance(path, Path):
            return str(path)
        try:
            return str(path.relative_to(self._config.project_path))
        except ValueError:
            return str(path)

    def _parse_links(
        self, file_index: dict[str, Path],
    ) -> tuple[list[tuple[Path, Path | str, bool]], set[Path | str]]:
        """Walk *selected_files* and extract (source, target, exists) tuples.

        ``target`` is a :class:`Path` when resolvable, otherwise the raw
        string from the wiki link.
        """
        links: list[tuple[Path, Path | str, bool]] = []
        all_targets: set[Path | str] = set()

        for source_file in self._config.selected_files:
            try:
                content = source_file.read_text(encoding="utf-8")
            except Exception:
                continue

            # Mask verbatim regions (code spans/blocks, math, HTML <pre>/
            # <script>/<style>, HTML comments) so the regexes below don't
            # treat `[[`, `]]`, `](`, `.md)` characters inside those regions
            # as link delimiters.
            content = mask_verbatim_regions(content)

            for match in WIKI_LINK_PATTERN.finditer(content):
                target = match.group(1).strip().lower()
                line_no = content[:match.start()].count('\n') + 1
                target_path = self.resolve_link(
                    target, source_file, file_index, line_number=line_no,
                )
                exists = target_path is not None and target_path.exists()
                resolved: Path | str = target_path if target_path is not None else target
                links.append((source_file, resolved, exists))
                all_targets.add(resolved)

            for match in MD_LINK_PATTERN.finditer(content):
                md_target = match.group(2).strip()
                # Resolve relative to the source file. Same ENAMETOOLONG
                # risk as wiki links if the masker missed something; guard
                # symmetrically.
                try:
                    target_path = (source_file.parent / md_target).resolve()
                    exists = target_path.exists()
                except OSError as e:
                    if e.errno == errno.ENAMETOOLONG:
                        line_no = content[:match.start()].count('\n') + 1
                        logger.warning(
                            "Skipping markdown link at %s:%d: target too long (%d chars)",
                            source_file, line_no, len(md_target),
                        )
                        continue
                    raise
                links.append((source_file, target_path, exists))
                all_targets.add(target_path)

        return links, all_targets

    def generate_dot(self) -> str:
        """Generate Graphviz DOT source for the configured graph."""
        cfg = self._config
        files = cfg.selected_files
        file_index = self.build_file_index()
        links, _ = self._parse_links(file_index)

        is_directed = cfg.is_directed
        graph_type = "digraph" if is_directed else "graph"
        edge_op = "->" if is_directed else "--"
        broken_handling = cfg.broken_handling
        labels_below = cfg.labels_below
        engine = cfg.engine

        lines = [f'{graph_type} DocumentGraph {{']
        lines.append('    rankdir=LR;')

        if labels_below:
            # Small node dots with separate labels; engine-specific spacing
            # to keep labels from overlapping.
            lines.append('    forcelabels=true;')
            lines.append('    node [shape=point, width=0.15, height=0.15];')
            lines.append('    graph [fontsize=10];')
            lines.append('    node [fontsize=10];')
            if engine == "dot":
                lines.append('    nodesep=0.8;')
                lines.append('    ranksep=1.0;')
            else:
                lines.append('    overlap=prism;')
                lines.append('    overlap_scaling=2;')
                lines.append('    sep="+20,20";')
        else:
            lines.append('    node [shape=box, style=rounded];')
        lines.append('')

        # Per-path node ids ──
        node_ids: dict[Path | str, str] = {}
        node_counter = 0

        def get_node_id(path: Path | str) -> str:
            nonlocal node_counter
            if path not in node_ids:
                node_ids[path] = f"n{node_counter}"
                node_counter += 1
            return node_ids[path]

        # Real file nodes (with URL for click handling).
        for f in files:
            node_id = get_node_id(f)
            label = self._get_label(f)
            tooltip = self._get_tooltip(f)
            url = str(f).replace('"', '\\"')
            if labels_below:
                lines.append(f'    {node_id} [shape=point, xlabel="{label}", tooltip="{tooltip}", URL="{url}"];')
            else:
                lines.append(f'    {node_id} [label="{label}", tooltip="{tooltip}", URL="{url}"];')

        # Broken-link target nodes.
        broken_nodes: set[Path | str] = set()
        for _source, target, exists in links:
            if exists:
                continue
            if broken_handling == "exclude":
                continue
            if target in broken_nodes:
                continue
            broken_nodes.add(target)
            node_id = get_node_id(target)
            label = self._get_label(target)
            tooltip = self._get_tooltip(target)
            if broken_handling == "red":
                if labels_below:
                    lines.append(f'    {node_id} [shape=point, xlabel="{label}", tooltip="{tooltip}", color=red];')
                else:
                    lines.append(f'    {node_id} [label="{label}", tooltip="{tooltip}", color=red, style="dashed,rounded"];')
            elif broken_handling == "warning":
                if labels_below:
                    lines.append(f'    {node_id} [shape=point, xlabel="{label}\\n(missing)", tooltip="{tooltip}", color=orange];')
                else:
                    lines.append(f'    {node_id} [label="{label}\\n(missing)", tooltip="{tooltip}", color=orange, style="filled,rounded", fillcolor=lightyellow];')
            else:  # "normal"
                if labels_below:
                    lines.append(f'    {node_id} [shape=point, xlabel="{label}", tooltip="{tooltip}"];')
                else:
                    lines.append(f'    {node_id} [label="{label}", tooltip="{tooltip}"];')

        lines.append('')

        # Edges (deduplicated).
        seen_edges: set[tuple[str, str]] = set()
        for source, target, exists in links:
            if not exists and broken_handling == "exclude":
                continue

            source_id = get_node_id(source)
            target_id = get_node_id(target)

            edge_key = (source_id, target_id) if is_directed else tuple(sorted([source_id, target_id]))
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)

            if exists or broken_handling == "normal":
                lines.append(f'    {source_id} {edge_op} {target_id};')
            else:
                lines.append(f'    {source_id} {edge_op} {target_id} [style=dashed, color=red];')

        lines.append('}')

        return '\n'.join(lines)

    # ── Rendering ───────────────────────────────────────────────────────

    def render_to_svg(self, dot_source: str) -> str:
        """Render DOT to SVG string. Applies dark mode if configured."""
        import graphviz
        graph = graphviz.Source(dot_source, engine=self._config.engine)
        svg = graph.pipe(format='svg').decode('utf-8')
        if self._config.dark_mode:
            svg = graphviz_service._apply_dark_mode(svg)
        return svg

    def render_to_png(self, dot_source: str, output_path: Path) -> None:
        """Render DOT to a PNG file at *output_path*."""
        import graphviz
        graph = graphviz.Source(dot_source, engine=self._config.engine)
        # graphviz.Source.render() appends the format extension itself.
        output_base = str(Path(output_path).with_suffix(""))
        graph.render(output_base, format='png', cleanup=True)

    def render_to_pdf(self, dot_source: str, output_path: Path) -> None:
        """Render DOT to a PDF file at *output_path*."""
        import graphviz
        graph = graphviz.Source(dot_source, engine=self._config.engine)
        output_base = str(Path(output_path).with_suffix(""))
        graph.render(output_base, format='pdf', cleanup=True)

    def render_to_dot(self, dot_source: str, output_path: Path) -> None:
        """Write the raw DOT source to *output_path*."""
        Path(output_path).write_text(dot_source, encoding="utf-8")

    def export(self, output_path: Path) -> str:
        """Generate DOT and write to *output_path* in the configured format.

        Returns the generated DOT source so callers (e.g. the GUI dialog
        showing a preview popup) can reuse it without re-running the
        generation pipeline.
        """
        dot_source = self.generate_dot()
        fmt = self._config.output_format
        if fmt == "svg":
            svg = self.render_to_svg(dot_source)
            Path(output_path).write_text(svg, encoding="utf-8")
        elif fmt == "png":
            self.render_to_png(dot_source, output_path)
        elif fmt == "pdf":
            self.render_to_pdf(dot_source, output_path)
        elif fmt == "dot":
            self.render_to_dot(dot_source, output_path)
        else:
            raise ValueError(f"Unknown output_format: {fmt!r}")
        return dot_source
