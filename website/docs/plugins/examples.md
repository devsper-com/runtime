---
title: Plugin Examples
---

# Plugin Examples

Three complete plugin examples, each with full project configuration, tool implementation, and usage instructions.

## Example 1: String Sanitizer Tool

A simple tool that strips HTML tags from text and returns clean plaintext.

### Project Structure

```
devsper-plugin-sanitizer/
  pyproject.toml
  sanitizer_plugin/
    __init__.py
```

### `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "devsper-plugin-sanitizer"
version = "0.1.0"
description = "HTML sanitizer tool for devsper"
requires-python = ">=3.10"
dependencies = ["devsper"]

[project.entry-points."devsper.plugins"]
sanitizer = "sanitizer_plugin:register_tools"
```

### `sanitizer_plugin/__init__.py`

```python
import re

from devsper.tools.base import Tool
from devsper.tools.registry import register


class SanitizeHtmlTool(Tool):
    name = "sanitize_html"
    description = "Remove HTML tags from text and return clean plaintext."
    input_schema = {
        "type": "object",
        "properties": {
            "html": {
                "type": "string",
                "description": "HTML content to sanitize"
            }
        },
        "required": ["html"]
    }

    def run(self, **kwargs) -> str:
        html = kwargs["html"]
        clean = re.sub(r"<[^>]+>", "", html)
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean


def register_tools():
    register(SanitizeHtmlTool())
```

### Usage

```bash
pip install -e .
devsper doctor  # Verify sanitize_html appears
```

```python
from sanitizer_plugin import SanitizeHtmlTool

tool = SanitizeHtmlTool()
result = tool.run(html="<p>Hello <b>world</b></p>")
print(result)  # Hello world
```

---

## Example 2: Weather API Tool

An API integration tool that fetches current weather data from the Open-Meteo API (no API key required).

### Project Structure

```
devsper-plugin-weather/
  pyproject.toml
  weather_plugin/
    __init__.py
```

### `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "devsper-plugin-weather"
version = "0.1.0"
description = "Weather lookup tool for devsper"
requires-python = ">=3.10"
dependencies = ["devsper", "httpx"]

[project.entry-points."devsper.plugins"]
weather = "weather_plugin:register_tools"
```

### `weather_plugin/__init__.py`

```python
import httpx

from devsper.tools.base import Tool
from devsper.tools.registry import register


class WeatherTool(Tool):
    name = "get_weather"
    description = "Get current weather for a location by latitude and longitude."
    input_schema = {
        "type": "object",
        "properties": {
            "latitude": {
                "type": "number",
                "description": "Latitude of the location"
            },
            "longitude": {
                "type": "number",
                "description": "Longitude of the location"
            }
        },
        "required": ["latitude", "longitude"]
    }

    def run(self, **kwargs) -> str:
        lat = kwargs["latitude"]
        lon = kwargs["longitude"]
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current_weather": True,
        }
        resp = httpx.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()["current_weather"]
        return (
            f"Temperature: {data['temperature']}C, "
            f"Wind speed: {data['windspeed']} km/h, "
            f"Condition code: {data['weathercode']}"
        )


def register_tools():
    register(WeatherTool())
```

### Usage

```bash
pip install -e .
devsper doctor  # Verify get_weather appears
```

```python
from weather_plugin import WeatherTool

tool = WeatherTool()
result = tool.run(latitude=37.77, longitude=-122.42)
print(result)  # Temperature: 18.2C, Wind speed: 12.3 km/h, Condition code: 3
```

---

## Example 3: CSV Profiler Tool

A file processing tool that reads a CSV file and returns summary statistics.

### Project Structure

```
devsper-plugin-csvprofile/
  pyproject.toml
  csvprofile_plugin/
    __init__.py
```

### `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "devsper-plugin-csvprofile"
version = "0.1.0"
description = "CSV profiling tool for devsper"
requires-python = ">=3.10"
dependencies = ["devsper"]

[project.entry-points."devsper.plugins"]
csvprofile = "csvprofile_plugin:register_tools"
```

### `csvprofile_plugin/__init__.py`

```python
import csv
import statistics

from devsper.tools.base import Tool
from devsper.tools.registry import register


class CsvProfileTool(Tool):
    name = "csv_profile"
    description = "Read a CSV file and return summary statistics for each numeric column."
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the CSV file"
            }
        },
        "required": ["file_path"]
    }

    def run(self, **kwargs) -> str:
        file_path = kwargs["file_path"]
        with open(file_path, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if not rows:
            return "Empty CSV file."

        columns = rows[0].keys()
        results = []
        results.append(f"Rows: {len(rows)}, Columns: {len(columns)}")

        for col in columns:
            values = []
            for row in rows:
                try:
                    values.append(float(row[col]))
                except (ValueError, TypeError):
                    continue
            if values:
                results.append(
                    f"{col}: min={min(values)}, max={max(values)}, "
                    f"mean={statistics.mean(values):.2f}, "
                    f"stdev={statistics.stdev(values):.2f}" if len(values) > 1
                    else f"{col}: min={min(values)}, max={max(values)}, "
                         f"mean={statistics.mean(values):.2f}"
                )

        return "\n".join(results)


def register_tools():
    register(CsvProfileTool())
```

### Usage

```bash
pip install -e .
devsper doctor  # Verify csv_profile appears
```

```python
from csvprofile_plugin import CsvProfileTool

tool = CsvProfileTool()
result = tool.run(file_path="data/sample.csv")
print(result)
```

---

## Common Patterns

### Error Handling

Always handle errors gracefully in `run()`. Return a descriptive error string rather than raising exceptions that would crash the swarm:

```python
def run(self, **kwargs) -> str:
    try:
        # tool logic
        return result
    except FileNotFoundError:
        return f"Error: file '{kwargs['file_path']}' not found."
    except Exception as e:
        return f"Error: {e}"
```

### Testing Locally

For any plugin, the testing workflow is the same:

```bash
pip install -e .          # Install in editable mode
devsper doctor           # Check registration
pytest                    # Run your test suite
```

### Adding Multiple Tools

A single plugin can register multiple tools:

```python
def register_tools():
    register(ToolA())
    register(ToolB())
    register(ToolC())
```

## Further Reading

- [Plugin Quickstart](/docs/plugins/quickstart) -- step-by-step guide to creating a plugin.
- [Tool Reference](/docs/plugins/tool-reference) -- browse built-in tool categories.
- [Publishing Plugins](/docs/plugins/publishing) -- share your plugin with the community.
- [Troubleshooting](/docs/plugins/troubleshooting) -- fix common issues.
