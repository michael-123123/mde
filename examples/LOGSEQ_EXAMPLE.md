- ## Architecture
	id:: d1e60b6d-5d26-4d0e-89ee-cd6c8d936f5b
	- ### Two-piece design
		id:: 57750f44-c16f-4862-bc45-60d76372e53a
		- ```
			id:: 12625238-cf1d-46de-a67d-ed428f0aa3f4
		  Claude Desktop ←(stdio JSON-RPC)→ ant.dir.gh.autodesk.fusion-mcp\index.js (50 LOC)
		                                              ↓
		                                    mcp-remote@0.1.38 (off-the-shelf Glen Maddern proxy)
		                                              ↓
		                                    HTTP/JSON-RPC → http://127.0.0.1:27182/mcp
		                                              ↓
		                                    Fusion's built-in MCP HTTP server (in-process)
		                                              ↓
		                                    Fusion API (CAD operations on main thread)
		  ```
- ## Open Questions
	- 1. What tools does Fusion's MCP actually expose? (Need a live `tools/list` response; not yet captured.)
	- 2. Does Fusion's MCP support the `AddCustomServer()` extensibility pattern Revit 2027 introduced, or is it locked to [[Autodesk]]'s built-in tools?
	- 3. Is there an audit log of MCP tool invocations on the Fusion side? Important if compliance-sensitive workflows are layered on top.
	- 4. When does the AutoCAD MCP ship, and through which channel (Anthropic Directory or [[Autodesk]] MSI)?
	- 5. When does the next Revit MCP capability bump ship, and does it follow the Anthropic Directory path or stay on [[Autodesk]]'s own distribution?
