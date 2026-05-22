---
name: text-search
description: Search and preview plain text files in the current folder tree. Use this when the task involves finding text in .txt, .md, .json, .csv, .log, .edf, config files, or source-like text files.
---

Use this skill when the user asks to inspect, preview, or search text content in one file or across many text files.

Scope and defaults:

- Stay in the current working directory and its child directories unless the user asks otherwise.
- Prefer common text-like files such as `.txt`, `.md`, `.json`, `.yaml`, `.yml`, `.csv`, `.tsv`, `.xml`, `.log`, `.edf`, `.ini`, `.cfg`, `.conf`, `.properties`, and source-like text files.
- Support `.EDF` and `.edf` files when they contain decodable text content.
- If the user already named a file, work on that file directly. Otherwise, discover candidate files first.

Workflow:

1. If needed, list text files in the current folder tree:

   ```bash
   python text_search.py list --root .
   ```

2. If the user wants to preview a file:

   ```bash
   python text_search.py preview path/to/file.txt --lines 20
   ```

3. If the user wants to search a specific file:

   ```bash
   python text_search.py search-file "needle" path/to/file.txt
   ```

4. If the user wants to search across many text files:

   ```bash
   python text_search.py search-tree "needle" --root .
   ```

Guidance:

- Report the file path, line number, and matching line for each result.
- If there are many matches, summarize by file first and show representative hits.
- Surface decoding problems explicitly instead of guessing silently.
- Use `--json` when another tool or app should consume the results programmatically.

Examples:

- "Search every text file here for database_url."
- "Preview the first 30 lines of `notes.txt`."
- "Find where `Input Voltage Range` appears in text files."
- "Search every `.EDF` file here for a status code."
