# Contributing

Use Python 3.14.2 or later in the 3.14 series. The test environment pins Home Assistant Core to 2026.11.3. Tests boot Core against temporary storage and a loopback server. They require no account, cloud API, physical panel or HA test-plugin override.

```sh
python3.14 -m venv .venv
. .venv/bin/activate
pip install -r requirements-test.txt
ruff check .
ruff format --check .
mypy custom_components/pixoo_doodle
python -m pytest --cov --cov-report=term-missing --cov-fail-under=95
python -m coverage report --include='*/config_flow.py' --fail-under=100
```

For a new device, include hardware number, firmware (when reported), method, port, path and sanitized response fields. Keep addresses, device IDs, MACs, account details and tokens out of fixtures, logs and screenshots. Start with reads. Coordinate visible writes with the owner and record the original state before changing it.

Add tests for supported and rejected inputs, model-specific commands and partial uploads. Update the capability profile, device matrix, action descriptions and English translations together. Artwork and fonts need licenses compatible with distribution in this repository.
