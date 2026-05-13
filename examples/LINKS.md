# Link detection — verbatim-region examples

Spec for what graph-export's link detection must (and must not) treat as a
link. Each bullet is marked with the expected outcome:

- `not link:` — no link should be detected on this line
- `link:` — exactly one link should be detected

## Inline code spans (single backticks)

- not link: `[[` hello
- not link: `[[CHANGELOG.md]]`
- not link: `[[CHANGELOG]]`
- not link: `[text](broken.md)`
- link: [[`CHANGELOG`]]
- link: [`text`](real.md)

## Inline code spans (multi-backtick variants)

- not link: ``[[has`backtick`inside]]``
- not link: ``` ``[[]]`` ```

## Fenced code blocks (triple backtick)

The whole block below is verbatim; neither bracket on any line is a link:

```
[[NotALinkInFence]]
[text](not-a-link.md)
```

## Fenced code blocks (tilde fences)

~~~
[[NotALinkInTildeFence]]
[text](not-a-link.md)
~~~

## Indented code blocks

The two lines below are indented with 4 spaces and follow a blank line — they
form an indented code block:

    [[NotALinkInIndented]]
    [text](not-a-link.md)

## Inline math

- not link: $[[x_{ij}]]$
- not link: $[a](b.md)$

## Display math

The matrix notation below uses `[[ ... ]]` and is **not** a wiki link:

$$
[[A_{ij}]] = \begin{bmatrix} 1 & 2 \\ 3 & 4 \end{bmatrix}
$$

## HTML — pre/script/style (verbatim per HTML spec)

- not link: <pre>[[NotALink]]</pre>
- not link: <script>[[NotALink]]</script>
- not link: <style>[[NotALink]]</style>

## HTML comments

- not link: <!-- [[NotALink]] -->
- not link: <!-- [text](not-a-link.md) -->

## Sanity — real links should still be detected

- link: [[RealWikiLink]]
- link: [[RealWikiLink|With Display]]
- link: [text](real-link.md)
- link: [text](path/to/real-link.md)
