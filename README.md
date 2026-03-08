# grip-dev

`grip-dev` is the development umbrella repository for GRIP Python work.

GitHub:
- `git@github.com:owebeeone/grip-dev.git`

## Clone

```bash
git clone --recursive git@github.com:owebeeone/grip-dev.git
cd grip-dev
```

If already cloned without submodules:

```bash
git submodule update --init --recursive
```

## Submodules

- `grip-py` -> `git@github.com:owebeeone/grip-py.git`
- `grip-py-demo` -> `git@github.com:owebeeone/grip-py-demo.git`

## Workspace Setup

Install dev-setup script dependencies:

```bash
pip install -r dev-setup/src/requirements.txt
```

Collect workspace runtime + test dependencies and install them into the active `uv` environment:

```bash
python dev-setup/src/collect_dependencies/collect_dependencies.py --workspace-root . --uv-install
```

Generate or refresh VS Code workspace config:

```bash
python dev-setup/src/vscode_configutator/vscode_configutator.py --workspace-root .
```

This manages:
- `.vscode/settings.json`
- `.vscode/launch.json`
- `.vscode/.env`
- `.vscode/local_settings.py`

## Spec

- `docs/GRIPPY_SPEC.md` contains the current package/API transition specification.
