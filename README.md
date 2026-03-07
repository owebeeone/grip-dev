# Grip Dev Tree

This repository is a development umbrella repo that holds submodules and maintenance
scripts for working on GRIP Python code as a multi-repo workspace.

## Clone Recursively

```bash
git clone --recursive <your-grip-dev-repo-url>
```

## Submodules

- `grip-py`: primary Python GRIP repository.

## VS Code Configuration

The workspace includes a `dev-setup` utility script to (re)generate:
- `.vscode/settings.json`
- `.vscode/launch.json`
- `.vscode/.env`
- `.vscode/local_settings.py`

Run:

```bash
python dev-setup/src/vscode_configutator/vscode_configutator.py --workspace-root .
```

To install script dependencies:

```bash
pip install -r dev-setup/src/requirements.txt
```

