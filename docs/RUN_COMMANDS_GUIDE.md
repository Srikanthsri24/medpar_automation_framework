# Running Commands from One Python File

Edit the root-level file:

```text
run_commands.py
```

Each command has:

```python
enabled=True
```

Set it to `False`, or comment out the command block, when it is not required. Change the stage, run date, source, actual, and expected paths directly in that file.

Run all enabled commands:

```cmd
python run_commands.py
```

The runner uses `sys.executable`, so it uses the Python from the active virtual environment. Forward slashes are used in paths because Python accepts them on Windows, Linux, and macOS.

## Modes

- `calculate`: validate one stage file and calculate known expected rules.
- `reconcile`: compare source data with application actual output.
- `golden`: compare source, application actual output, and approved expected output.

## All five stages

Enable this command in `run_commands.py`:

```python
Command(
    name="All five stages using the complete example manifest",
    args=[
        PYTHON,
        "-m",
        "medpar_qa.cli",
        "--manifest",
        "config/run_manifest.all_stages.example.yaml",
    ],
    enabled=True,
)
```

For your files, copy and edit:

```text
config/runs/all_5_stages_user_template.yaml
```

Then run:

```cmd
python -m medpar_qa.cli --manifest config/runs/all_5_stages_user_template.yaml
```

Do not leave a manifest path enabled when its folder has no matching files.
