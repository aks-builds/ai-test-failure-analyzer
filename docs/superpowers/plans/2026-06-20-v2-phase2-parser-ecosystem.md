# v2 Phase 2 — Parser Ecosystem Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 17 new parsers covering every major testing ecosystem so the tool works across any polyglot stack, all registered with `ParserRegistry`.

**Architecture:** Each parser lives in `analyzer/parsers/<name>.py`, implements the existing `Parser` ABC (`can_parse(sample) -> bool`, `parse(path) -> list[NormalizedFailure]`), and registers itself in `analyzer/parsers/__init__.py`. Each parser has a corresponding fixture file in `tests/analyzer/fixtures/` and test cases in `tests/analyzer/test_parsers.py`. Parsers are grouped into four batches for implementation.

**Tech Stack:** Python stdlib only — `json`, `xml.etree.ElementTree`, `re`, `pathlib`. No new deps.

## Global Constraints

- Python ≥ 3.10
- Every parser imports from `analyzer.parsers.base`: `NormalizedFailure`, `Parser`, `make_failure_id`, `parse_assertion`, `parse_http`
- `can_parse(sample)` receives a `bytes` object (first 4096 bytes of file). Decode with `sample.decode("utf-8", errors="replace")`
- Every `parse()` must return `list[NormalizedFailure]` — including passed/skipped tests, not just failures
- `make_failure_id(framework, suite, title, file)` generates the stable `id` field
- Fixture files live in `tests/analyzer/fixtures/` and must contain at least one failed test
- All new parsers must be registered in `analyzer/parsers/__init__.py` AND `analyzer/parsers/registry.py`
- `pytest tests/analyzer -q` must pass after every task

---

### Task 1: Web/JS parsers — Vitest, WDIO, Detox, Mocha

**Files:**
- Create: `analyzer/parsers/vitest_json.py`
- Create: `analyzer/parsers/wdio_json.py`
- Create: `analyzer/parsers/detox_json.py`
- Create: `analyzer/parsers/mocha_json.py`
- Create: `tests/analyzer/fixtures/vitest_results.json`
- Create: `tests/analyzer/fixtures/wdio_results.json`
- Create: `tests/analyzer/fixtures/detox_results.json`
- Create: `tests/analyzer/fixtures/mocha_results.json`
- Modify: `tests/analyzer/test_parsers.py`
- Modify: `analyzer/parsers/__init__.py`

**Interfaces:**
- Consumes: `Parser`, `NormalizedFailure`, `make_failure_id`, `parse_assertion`, `parse_http` from `analyzer.parsers.base`
- Produces: `VitestJsonParser` (framework=`"vitest"`), `WdioJsonParser` (framework=`"wdio"`), `DetoxJsonParser` (framework=`"detox"`), `MochaJsonParser` (framework=`"mocha"`)

- [ ] **Step 1: Create fixture files**

Create `tests/analyzer/fixtures/vitest_results.json`:
```json
{
  "vitestVersion": "1.6.0",
  "testResults": [
    {
      "testFilePath": "src/utils.test.ts",
      "assertionResults": [
        {
          "ancestorTitles": ["formatDate"],
          "fullName": "formatDate formats ISO string correctly",
          "status": "failed",
          "title": "formats ISO string correctly",
          "duration": 12,
          "failureMessages": ["Expected: \"2024-01-15\"\nReceived: \"01/15/2024\""]
        }
      ]
    }
  ]
}
```

Create `tests/analyzer/fixtures/wdio_results.json`:
```json
{
  "runner": "local",
  "capabilities": {"browserName": "chrome"},
  "suites": [
    {
      "name": "Login Suite",
      "tests": [
        {
          "name": "should login with valid credentials",
          "file": "test/specs/login.spec.js",
          "state": "failed",
          "duration": 3200,
          "error": {"message": "Element not found: #login-button", "stack": "Error: Element not found"}
        }
      ]
    }
  ]
}
```

Create `tests/analyzer/fixtures/detox_results.json`:
```json
{
  "artifactsLocation": "artifacts/",
  "device": {"type": "simulator", "name": "iPhone 15"},
  "testResults": [
    {
      "testFilePath": "e2e/login.test.js",
      "assertionResults": [
        {
          "ancestorTitles": ["Login"],
          "title": "should navigate to home screen",
          "status": "failed",
          "duration": 5100,
          "failureMessages": ["Timeout waiting for element with id 'homeScreen'"]
        }
      ]
    }
  ]
}
```

Create `tests/analyzer/fixtures/mocha_results.json`:
```json
{
  "stats": {"suites": 1, "tests": 2, "passes": 1, "failures": 1, "duration": 450},
  "passes": [
    {"fullTitle": "API health check returns 200", "duration": 120, "currentRetry": 0}
  ],
  "failures": [
    {
      "fullTitle": "API POST /users returns 201",
      "file": "test/api.spec.js",
      "duration": 330,
      "err": {
        "message": "AssertionError: expected 404 to equal 201",
        "stack": "AssertionError: expected 404 to equal 201\n    at test/api.spec.js:22:5"
      }
    }
  ],
  "pending": []
}
```

- [ ] **Step 2: Write failing tests**

Add to `tests/analyzer/test_parsers.py`:

```python
# ── Vitest ──────────────────────────────────────────────────────────────────

def test_vitest_can_parse(fixtures):
    from analyzer.parsers.vitest_json import VitestJsonParser
    assert VitestJsonParser.can_parse((fixtures / "vitest_results.json").read_bytes())


def test_vitest_cannot_parse_playwright(fixtures):
    from analyzer.parsers.vitest_json import VitestJsonParser
    assert not VitestJsonParser.can_parse((fixtures / "playwright_results.json").read_bytes())


def test_vitest_parse_returns_failures(fixtures):
    from analyzer.parsers.vitest_json import VitestJsonParser
    results = VitestJsonParser.parse(fixtures / "vitest_results.json")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert "formats ISO string correctly" in failed[0].title
    assert failed[0].framework == "vitest"


# ── WDIO ─────────────────────────────────────────────────────────────────────

def test_wdio_can_parse(fixtures):
    from analyzer.parsers.wdio_json import WdioJsonParser
    assert WdioJsonParser.can_parse((fixtures / "wdio_results.json").read_bytes())


def test_wdio_parse_returns_failures(fixtures):
    from analyzer.parsers.wdio_json import WdioJsonParser
    results = WdioJsonParser.parse(fixtures / "wdio_results.json")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].framework == "wdio"


# ── Detox ────────────────────────────────────────────────────────────────────

def test_detox_can_parse(fixtures):
    from analyzer.parsers.detox_json import DetoxJsonParser
    assert DetoxJsonParser.can_parse((fixtures / "detox_results.json").read_bytes())


def test_detox_parse_returns_failures(fixtures):
    from analyzer.parsers.detox_json import DetoxJsonParser
    results = DetoxJsonParser.parse(fixtures / "detox_results.json")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].framework == "detox"


# ── Mocha ────────────────────────────────────────────────────────────────────

def test_mocha_can_parse(fixtures):
    from analyzer.parsers.mocha_json import MochaJsonParser
    assert MochaJsonParser.can_parse((fixtures / "mocha_results.json").read_bytes())


def test_mocha_parse_returns_failures(fixtures):
    from analyzer.parsers.mocha_json import MochaJsonParser
    results = MochaJsonParser.parse(fixtures / "mocha_results.json")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert "POST /users" in failed[0].title
    assert failed[0].framework == "mocha"
```

(If `fixtures` fixture doesn't exist in `test_parsers.py`, add:)
```python
@pytest.fixture
def fixtures():
    return Path(__file__).parent / "fixtures"
```

- [ ] **Step 3: Run to verify failure**

```
pytest tests/analyzer/test_parsers.py::test_vitest_can_parse -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 4: Create `analyzer/parsers/vitest_json.py`**

```python
"""Vitest native JSON reporter parser."""
from __future__ import annotations
import json
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class VitestJsonParser(Parser):
    """Parses Vitest native JSON output (--reporter=json).
    Distinguishes from Jest by the top-level 'vitestVersion' key."""
    framework = "vitest"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return '"vitestVersion"' in text and '"testResults"' in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        data = json.loads(path.read_text(encoding="utf-8"))
        results: list[NormalizedFailure] = []
        for file_result in data.get("testResults", []):
            file_path = file_result.get("testFilePath", "unknown")
            for assertion in file_result.get("assertionResults", []):
                raw_status = assertion.get("status", "unknown")
                status = "failed" if raw_status == "failed" else (
                    "skipped" if raw_status in ("pending", "todo") else "passed"
                )
                suite = " > ".join(assertion.get("ancestorTitles", []))
                title = assertion.get("title", "")
                err_msgs = assertion.get("failureMessages", [])
                error_msg = err_msgs[0] if err_msgs else None
                expected, actual = parse_assertion(error_msg, None)
                http = parse_http(title, error_msg, None)
                results.append(NormalizedFailure(
                    id=make_failure_id("vitest", suite, title, file_path),
                    framework="vitest",
                    suite=suite or file_path,
                    title=title,
                    file=file_path,
                    duration_ms=assertion.get("duration"),
                    status=status,
                    error_message=error_msg,
                    expected=expected,
                    actual=actual,
                    http=http,
                    raw={k: v for k, v in assertion.items() if k != "failureMessages"},
                ))
        return results
```

- [ ] **Step 5: Create `analyzer/parsers/wdio_json.py`**

```python
"""WebdriverIO native JSON reporter parser."""
from __future__ import annotations
import json
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class WdioJsonParser(Parser):
    """Parses WebdriverIO JSON reporter output.
    Sniff: 'runner' + 'capabilities' + 'suites' keys."""
    framework = "wdio"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return '"runner"' in text and '"capabilities"' in text and '"suites"' in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        data = json.loads(path.read_text(encoding="utf-8"))
        results: list[NormalizedFailure] = []
        for suite in data.get("suites", []):
            suite_name = suite.get("name", "")
            for test in suite.get("tests", []):
                raw_state = test.get("state", "unknown")
                status = "failed" if raw_state == "failed" else (
                    "skipped" if raw_state == "skipped" else "passed"
                )
                title = test.get("name", "")
                file_path = test.get("file", "unknown")
                err = test.get("error") or {}
                error_msg = err.get("message")
                error_stack = err.get("stack")
                expected, actual = parse_assertion(error_msg, error_stack)
                http = parse_http(title, error_msg, error_stack)
                results.append(NormalizedFailure(
                    id=make_failure_id("wdio", suite_name, title, file_path),
                    framework="wdio",
                    suite=suite_name,
                    title=title,
                    file=file_path,
                    duration_ms=test.get("duration"),
                    status=status,
                    error_message=error_msg,
                    error_stack=error_stack,
                    expected=expected,
                    actual=actual,
                    http=http,
                    raw=test,
                ))
        return results
```

- [ ] **Step 6: Create `analyzer/parsers/detox_json.py`**

```python
"""Detox (React Native) JSON reporter parser."""
from __future__ import annotations
import json
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class DetoxJsonParser(Parser):
    """Parses Detox test runner JSON output.
    Sniff: 'testResults' + 'device' + 'artifactsLocation' keys."""
    framework = "detox"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return '"artifactsLocation"' in text and '"device"' in text and '"testResults"' in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        data = json.loads(path.read_text(encoding="utf-8"))
        results: list[NormalizedFailure] = []
        for file_result in data.get("testResults", []):
            file_path = file_result.get("testFilePath", "unknown")
            for assertion in file_result.get("assertionResults", []):
                raw_status = assertion.get("status", "unknown")
                status = "failed" if raw_status == "failed" else (
                    "skipped" if raw_status in ("pending", "todo") else "passed"
                )
                suite = " > ".join(assertion.get("ancestorTitles", []))
                title = assertion.get("title", "")
                err_msgs = assertion.get("failureMessages", [])
                error_msg = err_msgs[0] if err_msgs else None
                expected, actual = parse_assertion(error_msg, None)
                http = parse_http(title, error_msg, None)
                results.append(NormalizedFailure(
                    id=make_failure_id("detox", suite, title, file_path),
                    framework="detox",
                    suite=suite or file_path,
                    title=title,
                    file=file_path,
                    duration_ms=assertion.get("duration"),
                    status=status,
                    error_message=error_msg,
                    expected=expected,
                    actual=actual,
                    http=http,
                    raw={k: v for k, v in assertion.items() if k != "failureMessages"},
                ))
        return results
```

- [ ] **Step 7: Create `analyzer/parsers/mocha_json.py`**

```python
"""Mocha JSON reporter parser."""
from __future__ import annotations
import json
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class MochaJsonParser(Parser):
    """Parses Mocha --reporter=json output.
    Sniff: 'passes' + 'failures' + 'pending' as flat arrays (not nested suites)."""
    framework = "mocha"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        # Mocha JSON has flat 'passes', 'failures', 'pending' arrays at top level
        return ('"passes"' in text and '"failures"' in text and
                '"pending"' in text and '"suites"' not in text)

    @classmethod
    def _parse_test(cls, test: dict, status: str) -> NormalizedFailure:
        title = test.get("fullTitle") or test.get("title", "")
        file_path = test.get("file", "unknown")
        suite = test.get("titlePath", [title])[0] if test.get("titlePath") else title.rsplit(" ", 1)[0]
        err = test.get("err") or {}
        error_msg = err.get("message")
        error_stack = err.get("stack")
        expected, actual = parse_assertion(error_msg, error_stack)
        http = parse_http(title, error_msg, error_stack)
        return NormalizedFailure(
            id=make_failure_id("mocha", suite, title, file_path),
            framework="mocha",
            suite=suite,
            title=title,
            file=file_path,
            duration_ms=test.get("duration"),
            status=status,
            error_message=error_msg,
            error_stack=error_stack,
            expected=expected,
            actual=actual,
            http=http,
            raw=test,
        )

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        data = json.loads(path.read_text(encoding="utf-8"))
        results: list[NormalizedFailure] = []
        for test in data.get("passes", []):
            results.append(cls._parse_test(test, "passed"))
        for test in data.get("failures", []):
            results.append(cls._parse_test(test, "failed"))
        for test in data.get("pending", []):
            results.append(cls._parse_test(test, "skipped"))
        return results
```

- [ ] **Step 8: Register new parsers in `analyzer/parsers/__init__.py`**

Add imports after existing imports:
```python
from .vitest_json import VitestJsonParser
from .wdio_json import WdioJsonParser
from .detox_json import DetoxJsonParser
from .mocha_json import MochaJsonParser
```

Add to `PARSERS` list (before `JestJsonParser` — Vitest must precede Jest):
```python
    VitestJsonParser,   # before Jest — "vitestVersion" key distinguishes
    WdioJsonParser,
    DetoxJsonParser,
    MochaJsonParser,
```

Add to `FRAMEWORKS` dict:
```python
    "vitest": VitestJsonParser,
    "wdio": WdioJsonParser,
    "webdriverio": WdioJsonParser,
    "detox": DetoxJsonParser,
    "mocha": MochaJsonParser,
```

Also register in `_Registry` calls:
```python
_Registry.register(VitestJsonParser, aliases=["vitest"])
_Registry.register(WdioJsonParser,   aliases=["wdio", "webdriverio"])
_Registry.register(DetoxJsonParser,  aliases=["detox"])
_Registry.register(MochaJsonParser,  aliases=["mocha"])
```

- [ ] **Step 9: Run tests**

```
pytest tests/analyzer/test_parsers.py -v -k "vitest or wdio or detox or mocha"
```
Expected: all pass.

- [ ] **Step 10: Run full suite**

```
pytest tests/analyzer -q
```
Expected: all pass.

- [ ] **Step 11: Commit**

```
git add analyzer/parsers/vitest_json.py analyzer/parsers/wdio_json.py analyzer/parsers/detox_json.py analyzer/parsers/mocha_json.py tests/analyzer/fixtures/vitest_results.json tests/analyzer/fixtures/wdio_results.json tests/analyzer/fixtures/detox_results.json tests/analyzer/fixtures/mocha_results.json tests/analyzer/test_parsers.py analyzer/parsers/__init__.py
git commit -m "feat(v2): add Vitest, WDIO, Detox, Mocha parsers"
```

---

### Task 2: Backend/polyglot parsers — Go, RSpec, PHPUnit, NUnit, xUnit, Robot Framework

**Files:**
- Create: `analyzer/parsers/go_test_json.py`
- Create: `analyzer/parsers/rspec_json.py`
- Create: `analyzer/parsers/phpunit_xml.py`
- Create: `analyzer/parsers/nunit_xml.py`
- Create: `analyzer/parsers/xunit_xml.py`
- Create: `analyzer/parsers/robot_xml.py`
- Create: `tests/analyzer/fixtures/go_test_results.ndjson`
- Create: `tests/analyzer/fixtures/rspec_results.json`
- Create: `tests/analyzer/fixtures/phpunit_results.xml`
- Create: `tests/analyzer/fixtures/nunit_results.xml`
- Create: `tests/analyzer/fixtures/xunit_results.xml`
- Create: `tests/analyzer/fixtures/robot_results.xml`
- Modify: `tests/analyzer/test_parsers.py`, `analyzer/parsers/__init__.py`

**Interfaces:**
- Produces: `GoTestJsonParser` (framework=`"go"`), `RSpecJsonParser` (framework=`"rspec"`), `PHPUnitXmlParser` (framework=`"phpunit"`), `NUnitXmlParser` (framework=`"nunit"`), `XUnitXmlParser` (framework=`"xunit"`), `RobotXmlParser` (framework=`"robot"`)

- [ ] **Step 1: Create fixture files**

Create `tests/analyzer/fixtures/go_test_results.ndjson` (NDJSON — one JSON object per line):
```
{"Time":"2024-01-15T10:00:00Z","Action":"run","Package":"github.com/example/api","Test":"TestCreateUser"}
{"Time":"2024-01-15T10:00:00Z","Action":"output","Package":"github.com/example/api","Test":"TestCreateUser","Output":"--- FAIL: TestCreateUser (0.12s)\n"}
{"Time":"2024-01-15T10:00:00Z","Action":"output","Package":"github.com/example/api","Test":"TestCreateUser","Output":"    api_test.go:45: expected status 201, got 404\n"}
{"Time":"2024-01-15T10:00:00Z","Action":"fail","Package":"github.com/example/api","Test":"TestCreateUser","Elapsed":0.12}
{"Time":"2024-01-15T10:00:01Z","Action":"run","Package":"github.com/example/api","Test":"TestGetUser"}
{"Time":"2024-01-15T10:00:01Z","Action":"pass","Package":"github.com/example/api","Test":"TestGetUser","Elapsed":0.05}
```

Create `tests/analyzer/fixtures/rspec_results.json`:
```json
{
  "version": "3.12.0",
  "summary_line": "2 examples, 1 failure",
  "summary": {"example_count": 2, "failure_count": 1, "duration": 0.45},
  "examples": [
    {
      "id": "./spec/api/users_spec.rb[1:1]",
      "description": "creates a user successfully",
      "full_description": "UsersAPI POST /users creates a user successfully",
      "status": "failed",
      "file_path": "./spec/api/users_spec.rb",
      "line_number": 12,
      "run_time": 0.23,
      "exception": {
        "class": "RSpec::Expectations::ExpectationNotMetError",
        "message": "expected the response to have status code 201 but it was 404"
      }
    },
    {
      "id": "./spec/api/users_spec.rb[1:2]",
      "description": "returns 200 for existing user",
      "full_description": "UsersAPI GET /users/:id returns 200 for existing user",
      "status": "passed",
      "file_path": "./spec/api/users_spec.rb",
      "line_number": 25,
      "run_time": 0.22
    }
  ]
}
```

Create `tests/analyzer/fixtures/phpunit_results.xml`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<phpunit version="10.5.0">
  <testsuites>
    <testsuite name="App\Tests\UserControllerTest" tests="2" failures="1" errors="0" time="0.234">
      <testcase name="testCreateUserReturns201" class="App\Tests\UserControllerTest" file="tests/UserControllerTest.php" line="15" time="0.123">
        <failure type="PHPUnit\Framework\ExpectationFailedException">Failed asserting that 404 matches expected 201.</failure>
      </testcase>
      <testcase name="testGetUserReturns200" class="App\Tests\UserControllerTest" file="tests/UserControllerTest.php" line="30" time="0.111"/>
    </testsuite>
  </testsuites>
</phpunit>
```

Create `tests/analyzer/fixtures/nunit_results.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<test-run id="1" name="MyTests" total="2" passed="1" failed="1" duration="0.45" engine-version="3.16.3">
  <test-suite type="Assembly" name="MyTests.dll">
    <test-suite type="TestFixture" name="UserTests" fullname="MyTests.UserTests">
      <test-case id="1-1" name="CreateUser_Returns201" fullname="MyTests.UserTests.CreateUser_Returns201"
                 result="Failed" duration="0.23" methodname="CreateUser_Returns201" classname="MyTests.UserTests">
        <failure>
          <message>Expected: 201  But was: 404</message>
          <stack-trace>at MyTests.UserTests.CreateUser_Returns201() in UserTests.cs:line 22</stack-trace>
        </failure>
      </test-case>
      <test-case id="1-2" name="GetUser_Returns200" fullname="MyTests.UserTests.GetUser_Returns200"
                 result="Passed" duration="0.22"/>
    </test-suite>
  </test-suite>
</test-run>
```

Create `tests/analyzer/fixtures/xunit_results.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<assemblies>
  <assembly name="MyTests.dll" run-date="2024-01-15" run-time="10:00:00" total="2" passed="1" failed="1" time="0.45">
    <collection name="Test collection" total="2" passed="1" failed="1" time="0.45">
      <test name="MyTests.UserTests.CreateUser_Returns201" type="MyTests.UserTests" method="CreateUser_Returns201" time="0.23" result="Fail">
        <failure exception-type="Xunit.Sdk.EqualException">
          <message>Assert.Equal() Failure: Values differ. Expected: 201. Actual: 404</message>
          <stack-trace>at MyTests.UserTests.CreateUser_Returns201() in UserTests.cs:line 18</stack-trace>
        </failure>
      </test>
      <test name="MyTests.UserTests.GetUser_Returns200" type="MyTests.UserTests" method="GetUser_Returns200" time="0.22" result="Pass"/>
    </collection>
  </assembly>
</assemblies>
```

Create `tests/analyzer/fixtures/robot_results.xml`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<robot generator="Robot 6.1.1" generated="20240115 10:00:00.000">
  <suite name="API Tests" source="tests/api_tests.robot">
    <test name="Create User Returns 201" id="s1-t1">
      <kw name="POST" library="RequestsLibrary">
        <msg timestamp="20240115 10:00:01.000" level="FAIL">AssertionError: 404 != 201</msg>
      </kw>
      <status status="FAIL" starttime="20240115 10:00:00.000" endtime="20240115 10:00:01.234">
        AssertionError: 404 != 201
      </status>
    </test>
    <test name="Get User Returns 200" id="s1-t2">
      <status status="PASS" starttime="20240115 10:00:02.000" endtime="20240115 10:00:02.500"/>
    </test>
  </suite>
  <statistics/>
  <errors/>
</robot>
```

- [ ] **Step 2: Write failing tests**

Add to `tests/analyzer/test_parsers.py`:

```python
# ── Go test JSON ──────────────────────────────────────────────────────────────

def test_go_test_can_parse(fixtures):
    from analyzer.parsers.go_test_json import GoTestJsonParser
    assert GoTestJsonParser.can_parse((fixtures / "go_test_results.ndjson").read_bytes())


def test_go_test_cannot_parse_json_object(fixtures):
    from analyzer.parsers.go_test_json import GoTestJsonParser
    assert not GoTestJsonParser.can_parse(b'{"testResults": []}')


def test_go_test_parse_returns_failures(fixtures):
    from analyzer.parsers.go_test_json import GoTestJsonParser
    results = GoTestJsonParser.parse(fixtures / "go_test_results.ndjson")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert "TestCreateUser" in failed[0].title
    assert failed[0].framework == "go"
    assert "404" in (failed[0].error_message or "")


# ── RSpec ─────────────────────────────────────────────────────────────────────

def test_rspec_can_parse(fixtures):
    from analyzer.parsers.rspec_json import RSpecJsonParser
    assert RSpecJsonParser.can_parse((fixtures / "rspec_results.json").read_bytes())


def test_rspec_parse_returns_failures(fixtures):
    from analyzer.parsers.rspec_json import RSpecJsonParser
    results = RSpecJsonParser.parse(fixtures / "rspec_results.json")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].framework == "rspec"
    assert failed[0].line == 12


# ── PHPUnit ───────────────────────────────────────────────────────────────────

def test_phpunit_can_parse(fixtures):
    from analyzer.parsers.phpunit_xml import PHPUnitXmlParser
    assert PHPUnitXmlParser.can_parse((fixtures / "phpunit_results.xml").read_bytes())


def test_phpunit_parse_returns_failures(fixtures):
    from analyzer.parsers.phpunit_xml import PHPUnitXmlParser
    results = PHPUnitXmlParser.parse(fixtures / "phpunit_results.xml")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].framework == "phpunit"


# ── NUnit ─────────────────────────────────────────────────────────────────────

def test_nunit_can_parse(fixtures):
    from analyzer.parsers.nunit_xml import NUnitXmlParser
    assert NUnitXmlParser.can_parse((fixtures / "nunit_results.xml").read_bytes())


def test_nunit_parse_returns_failures(fixtures):
    from analyzer.parsers.nunit_xml import NUnitXmlParser
    results = NUnitXmlParser.parse(fixtures / "nunit_results.xml")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].framework == "nunit"


# ── xUnit ─────────────────────────────────────────────────────────────────────

def test_xunit_can_parse(fixtures):
    from analyzer.parsers.xunit_xml import XUnitXmlParser
    assert XUnitXmlParser.can_parse((fixtures / "xunit_results.xml").read_bytes())


def test_xunit_parse_returns_failures(fixtures):
    from analyzer.parsers.xunit_xml import XUnitXmlParser
    results = XUnitXmlParser.parse(fixtures / "xunit_results.xml")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].framework == "xunit"


# ── Robot Framework ───────────────────────────────────────────────────────────

def test_robot_can_parse(fixtures):
    from analyzer.parsers.robot_xml import RobotXmlParser
    assert RobotXmlParser.can_parse((fixtures / "robot_results.xml").read_bytes())


def test_robot_parse_returns_failures(fixtures):
    from analyzer.parsers.robot_xml import RobotXmlParser
    results = RobotXmlParser.parse(fixtures / "robot_results.xml")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert "Create User" in failed[0].title
    assert failed[0].framework == "robot"
```

- [ ] **Step 3: Run to verify failure**

```
pytest tests/analyzer/test_parsers.py::test_go_test_can_parse -v
```
Expected: `ERROR` — module not found.

- [ ] **Step 4: Create `analyzer/parsers/go_test_json.py`**

```python
"""Go test -json (NDJSON) parser."""
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class GoTestJsonParser(Parser):
    """Parses `go test -json` NDJSON output (one JSON object per line).
    Sniff: first line contains '{"Action":'."""
    framework = "go"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        first_line = sample.split(b"\n")[0].strip()
        try:
            obj = json.loads(first_line)
            return "Action" in obj and "Package" in obj
        except (json.JSONDecodeError, ValueError):
            return False

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        # Accumulate output lines per test, emit on pass/fail action
        outputs: dict[str, list[str]] = defaultdict(list)
        results: list[NormalizedFailure] = []
        elapsed: dict[str, float] = {}

        with open(path, encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    event = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                action = event.get("Action", "")
                pkg = event.get("Package", "")
                test = event.get("Test")
                if not test:
                    continue  # package-level events
                key = f"{pkg}::{test}"
                if action == "output":
                    outputs[key].append(event.get("Output", ""))
                elif action in ("pass", "fail", "skip"):
                    elapsed[key] = event.get("Elapsed", 0)
                    status = "failed" if action == "fail" else (
                        "skipped" if action == "skip" else "passed"
                    )
                    error_msg = "".join(outputs.get(key, [])).strip() or None
                    expected, actual = parse_assertion(error_msg, None)
                    http = parse_http(test, error_msg, None)
                    results.append(NormalizedFailure(
                        id=make_failure_id("go", pkg, test, pkg),
                        framework="go",
                        suite=pkg,
                        title=test,
                        file=pkg,
                        duration_ms=int(elapsed.get(key, 0) * 1000),
                        status=status,
                        error_message=error_msg,
                        expected=expected,
                        actual=actual,
                        http=http,
                        raw=event,
                    ))
        return results
```

- [ ] **Step 5: Create `analyzer/parsers/rspec_json.py`**

```python
"""RSpec JSON formatter parser."""
from __future__ import annotations
import json
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class RSpecJsonParser(Parser):
    """Parses RSpec --format json output.
    Sniff: 'version' + 'examples' + 'summary_line'."""
    framework = "rspec"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return '"summary_line"' in text and '"examples"' in text and '"version"' in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        data = json.loads(path.read_text(encoding="utf-8"))
        results: list[NormalizedFailure] = []
        for ex in data.get("examples", []):
            raw_status = ex.get("status", "unknown")
            status = "failed" if raw_status == "failed" else (
                "skipped" if raw_status == "pending" else "passed"
            )
            title = ex.get("full_description") or ex.get("description", "")
            file_path = ex.get("file_path", "unknown")
            exc = ex.get("exception") or {}
            error_msg = exc.get("message")
            expected, actual = parse_assertion(error_msg, None)
            http = parse_http(title, error_msg, None)
            results.append(NormalizedFailure(
                id=make_failure_id("rspec", ex.get("id", ""), title, file_path),
                framework="rspec",
                suite=file_path,
                title=title,
                file=file_path,
                line=ex.get("line_number"),
                duration_ms=int((ex.get("run_time") or 0) * 1000),
                status=status,
                error_message=error_msg,
                expected=expected,
                actual=actual,
                http=http,
                raw=ex,
            ))
        return results
```

- [ ] **Step 6: Create `analyzer/parsers/phpunit_xml.py`**

```python
"""PHPUnit XML results parser."""
from __future__ import annotations
from pathlib import Path
import xml.etree.ElementTree as ET
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class PHPUnitXmlParser(Parser):
    """Parses PHPUnit XML output (--log-junit or default).
    Sniff: <phpunit> root element."""
    framework = "phpunit"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return "<phpunit" in text and "<testsuite" in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        root = ET.parse(str(path)).getroot()
        results: list[NormalizedFailure] = []
        for tc in root.iter("testcase"):
            suite = tc.get("class") or tc.get("classname") or ""
            title = tc.get("name", "")
            file_path = tc.get("file", "unknown")
            line = int(tc.get("line", 0)) or None
            duration_ms = int(float(tc.get("time", 0)) * 1000)
            failure = tc.find("failure") or tc.find("error")
            if failure is not None:
                error_msg = failure.text or failure.get("type") or ""
                expected, actual = parse_assertion(error_msg, None)
                http = parse_http(title, error_msg, None)
                status = "failed"
            else:
                error_msg = expected = actual = http = None
                status = "skipped" if tc.find("skipped") is not None else "passed"
            results.append(NormalizedFailure(
                id=make_failure_id("phpunit", suite, title, file_path),
                framework="phpunit",
                suite=suite,
                title=title,
                file=file_path,
                line=line,
                duration_ms=duration_ms,
                status=status,
                error_message=error_msg,
                expected=expected,
                actual=actual,
                http=http,
                raw={"class": suite, "name": title},
            ))
        return results
```

- [ ] **Step 7: Create `analyzer/parsers/nunit_xml.py`**

```python
"""NUnit 3 XML results parser."""
from __future__ import annotations
from pathlib import Path
import xml.etree.ElementTree as ET
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class NUnitXmlParser(Parser):
    """Parses NUnit 3 XML output.
    Sniff: <test-run> root element with engine-version attribute."""
    framework = "nunit"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return "<test-run" in text and "engine-version" in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        root = ET.parse(str(path)).getroot()
        results: list[NormalizedFailure] = []
        for tc in root.iter("test-case"):
            raw_result = tc.get("result", "Unknown")
            status = "failed" if raw_result == "Failed" else (
                "skipped" if raw_result in ("Skipped", "Ignored") else "passed"
            )
            fullname = tc.get("fullname") or tc.get("name", "")
            classname = tc.get("classname") or fullname.rsplit(".", 1)[0]
            title = tc.get("name") or tc.get("methodname", "")
            failure_el = tc.find("failure")
            error_msg = error_stack = None
            if failure_el is not None:
                msg_el = failure_el.find("message")
                st_el = failure_el.find("stack-trace")
                error_msg = msg_el.text if msg_el is not None else None
                error_stack = st_el.text if st_el is not None else None
            expected, actual = parse_assertion(error_msg, error_stack)
            http = parse_http(title, error_msg, error_stack)
            duration_ms = int(float(tc.get("duration", 0)) * 1000)
            results.append(NormalizedFailure(
                id=make_failure_id("nunit", classname, title, classname),
                framework="nunit",
                suite=classname,
                title=title,
                file=classname,
                duration_ms=duration_ms,
                status=status,
                error_message=error_msg,
                error_stack=error_stack,
                expected=expected,
                actual=actual,
                http=http,
                raw={"fullname": fullname},
            ))
        return results
```

- [ ] **Step 8: Create `analyzer/parsers/xunit_xml.py`**

```python
"""xUnit.net XML results parser."""
from __future__ import annotations
from pathlib import Path
import xml.etree.ElementTree as ET
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class XUnitXmlParser(Parser):
    """Parses xUnit.net XML output.
    Sniff: <assemblies> root element."""
    framework = "xunit"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return "<assemblies" in text and "<collection" in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        root = ET.parse(str(path)).getroot()
        results: list[NormalizedFailure] = []
        for test in root.iter("test"):
            raw_result = test.get("result", "Unknown")
            status = "failed" if raw_result in ("Fail", "Error") else (
                "skipped" if raw_result == "Skip" else "passed"
            )
            name = test.get("name", "")
            type_ = test.get("type", "")
            method = test.get("method", "")
            title = method or name
            failure_el = test.find("failure")
            error_msg = error_stack = None
            if failure_el is not None:
                msg_el = failure_el.find("message")
                st_el = failure_el.find("stack-trace")
                error_msg = msg_el.text if msg_el is not None else None
                error_stack = st_el.text if st_el is not None else None
            expected, actual = parse_assertion(error_msg, error_stack)
            http = parse_http(title, error_msg, error_stack)
            duration_ms = int(float(test.get("time", 0)) * 1000)
            results.append(NormalizedFailure(
                id=make_failure_id("xunit", type_, title, type_),
                framework="xunit",
                suite=type_,
                title=title,
                file=type_,
                duration_ms=duration_ms,
                status=status,
                error_message=error_msg,
                error_stack=error_stack,
                expected=expected,
                actual=actual,
                http=http,
                raw={"name": name},
            ))
        return results
```

- [ ] **Step 9: Create `analyzer/parsers/robot_xml.py`**

```python
"""Robot Framework XML results parser."""
from __future__ import annotations
from pathlib import Path
import xml.etree.ElementTree as ET
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class RobotXmlParser(Parser):
    """Parses Robot Framework output.xml.
    Sniff: <robot generator="Robot ..."> root element."""
    framework = "robot"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return "<robot" in text and 'generator="Robot' in text

    @classmethod
    def _parse_suite(cls, suite_el, results, suite_name=""):
        name = suite_el.get("name", suite_name)
        for test in suite_el.findall("test"):
            test_name = test.get("name", "")
            status_el = test.find("status")
            if status_el is None:
                continue
            raw_status = status_el.get("status", "UNKNOWN")
            status = "failed" if raw_status == "FAIL" else (
                "skipped" if raw_status == "SKIP" else "passed"
            )
            error_msg = (status_el.text or "").strip() or None
            # Collect FAIL messages from keywords
            if not error_msg:
                for msg in test.iter("msg"):
                    if msg.get("level") == "FAIL":
                        error_msg = msg.text
                        break
            expected, actual = parse_assertion(error_msg, None)
            http = parse_http(test_name, error_msg, None)
            source = suite_el.get("source", "unknown")
            results.append(NormalizedFailure(
                id=make_failure_id("robot", name, test_name, source),
                framework="robot",
                suite=name,
                title=test_name,
                file=source,
                status=status,
                error_message=error_msg,
                expected=expected,
                actual=actual,
                http=http,
                raw={"suite": name},
            ))
        for child_suite in suite_el.findall("suite"):
            cls._parse_suite(child_suite, results, name)

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        root = ET.parse(str(path)).getroot()
        results: list[NormalizedFailure] = []
        for suite in root.findall("suite"):
            cls._parse_suite(suite, results)
        return results
```

- [ ] **Step 10: Register parsers in `analyzer/parsers/__init__.py`**

Add imports:
```python
from .go_test_json import GoTestJsonParser
from .rspec_json import RSpecJsonParser
from .phpunit_xml import PHPUnitXmlParser
from .nunit_xml import NUnitXmlParser
from .xunit_xml import XUnitXmlParser
from .robot_xml import RobotXmlParser
```

Add to `PARSERS` list (before `JUnitXmlParser` fallback):
```python
    GoTestJsonParser,
    RSpecJsonParser,
    PHPUnitXmlParser,
    NUnitXmlParser,
    XUnitXmlParser,
    RobotXmlParser,
```

Add to `FRAMEWORKS` dict:
```python
    "go": GoTestJsonParser, "gotest": GoTestJsonParser,
    "rspec": RSpecJsonParser,
    "phpunit": PHPUnitXmlParser,
    "nunit": NUnitXmlParser,
    "xunit": XUnitXmlParser,
    "robot": RobotXmlParser, "robotframework": RobotXmlParser,
```

Add `_Registry.register(...)` calls for each.

- [ ] **Step 11: Run tests**

```
pytest tests/analyzer/test_parsers.py -v -k "go_test or rspec or phpunit or nunit or xunit or robot"
pytest tests/analyzer -q
```
Expected: all pass.

- [ ] **Step 12: Commit**

```
git add analyzer/parsers/go_test_json.py analyzer/parsers/rspec_json.py analyzer/parsers/phpunit_xml.py analyzer/parsers/nunit_xml.py analyzer/parsers/xunit_xml.py analyzer/parsers/robot_xml.py tests/analyzer/fixtures/ tests/analyzer/test_parsers.py analyzer/parsers/__init__.py
git commit -m "feat(v2): add Go, RSpec, PHPUnit, NUnit, xUnit, Robot Framework parsers"
```

---

### Task 3: API/load/contract parsers — Artillery, Gatling, Pact

**Files:**
- Create: `analyzer/parsers/artillery_json.py`
- Create: `analyzer/parsers/gatling_log.py`
- Create: `analyzer/parsers/pact_json.py`
- Create: `tests/analyzer/fixtures/artillery_results.json`
- Create: `tests/analyzer/fixtures/gatling_simulation.log`
- Create: `tests/analyzer/fixtures/pact_results.json`
- Modify: `tests/analyzer/test_parsers.py`, `analyzer/parsers/__init__.py`

**Interfaces:**
- Produces: `ArtilleryJsonParser` (framework=`"artillery"`), `GatlingLogParser` (framework=`"gatling"`), `PactJsonParser` (framework=`"pact"`)

- [ ] **Step 1: Create fixture files**

Create `tests/analyzer/fixtures/artillery_results.json`:
```json
{
  "aggregate": {
    "scenariosCreated": 100,
    "scenariosCompleted": 85,
    "requestsCompleted": 85,
    "codes": {"200": 70, "404": 15},
    "errors": {"ECONNREFUSED": 5},
    "customStats": {}
  },
  "intermediate": [],
  "scenariosCreated": 100
}
```

Create `tests/analyzer/fixtures/gatling_simulation.log` (TSV):
```
RUN	GatlingSimulation	gatling-simulation	1705312800000	My Simulation	3.9.5
REQUEST		1705312800100	1705312800350	POST /api/users	OK
REQUEST		1705312800400	1705312801200	POST /api/users/register	KO	Status 404 expected 201
REQUEST		1705312801300	1705312801450	GET /api/users/1	OK
END
```

Create `tests/analyzer/fixtures/pact_results.json`:
```json
{
  "consumer": {"name": "frontend-app"},
  "provider": {"name": "user-api"},
  "interactions": [
    {
      "description": "a request to create a user",
      "providerState": "no users exist",
      "request": {"method": "POST", "path": "/api/users"},
      "response": {"status": 201},
      "verified": false,
      "verificationError": "Expected status 201 but got 404"
    },
    {
      "description": "a request to get existing user",
      "request": {"method": "GET", "path": "/api/users/1"},
      "response": {"status": 200},
      "verified": true
    }
  ]
}
```

- [ ] **Step 2: Write failing tests**

Add to `tests/analyzer/test_parsers.py`:

```python
# ── Artillery ─────────────────────────────────────────────────────────────────

def test_artillery_can_parse(fixtures):
    from analyzer.parsers.artillery_json import ArtilleryJsonParser
    assert ArtilleryJsonParser.can_parse((fixtures / "artillery_results.json").read_bytes())


def test_artillery_parse_returns_failures(fixtures):
    from analyzer.parsers.artillery_json import ArtilleryJsonParser
    results = ArtilleryJsonParser.parse(fixtures / "artillery_results.json")
    # Artillery reports aggregate errors as failures
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) >= 1
    assert failed[0].framework == "artillery"


# ── Gatling ───────────────────────────────────────────────────────────────────

def test_gatling_can_parse(fixtures):
    from analyzer.parsers.gatling_log import GatlingLogParser
    assert GatlingLogParser.can_parse((fixtures / "gatling_simulation.log").read_bytes())


def test_gatling_cannot_parse_json(fixtures):
    from analyzer.parsers.gatling_log import GatlingLogParser
    assert not GatlingLogParser.can_parse(b'{"testResults": []}')


def test_gatling_parse_returns_failures(fixtures):
    from analyzer.parsers.gatling_log import GatlingLogParser
    results = GatlingLogParser.parse(fixtures / "gatling_simulation.log")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert "/api/users/register" in failed[0].title
    assert failed[0].framework == "gatling"


# ── Pact ──────────────────────────────────────────────────────────────────────

def test_pact_can_parse(fixtures):
    from analyzer.parsers.pact_json import PactJsonParser
    assert PactJsonParser.can_parse((fixtures / "pact_results.json").read_bytes())


def test_pact_parse_returns_failures(fixtures):
    from analyzer.parsers.pact_json import PactJsonParser
    results = PactJsonParser.parse(fixtures / "pact_results.json")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert "create a user" in failed[0].title
    assert failed[0].framework == "pact"
```

- [ ] **Step 3: Create `analyzer/parsers/artillery_json.py`**

```python
"""Artillery JSON summary parser."""
from __future__ import annotations
import json
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_http


class ArtilleryJsonParser(Parser):
    """Parses Artillery --output JSON summary files.
    Sniff: 'aggregate' + 'scenariosCreated' top-level keys."""
    framework = "artillery"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return '"aggregate"' in text and '"scenariosCreated"' in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        data = json.loads(path.read_text(encoding="utf-8"))
        agg = data.get("aggregate", {})
        results: list[NormalizedFailure] = []

        # Each error type becomes a failure
        for error_type, count in (agg.get("errors") or {}).items():
            title = f"Artillery error: {error_type} ({count} occurrences)"
            http = parse_http(title, error_type, None)
            results.append(NormalizedFailure(
                id=make_failure_id("artillery", "aggregate", title, "simulation"),
                framework="artillery",
                suite="aggregate",
                title=title,
                file="simulation",
                status="failed",
                error_message=f"{count} occurrences of {error_type}",
                http=http,
                raw={"error": error_type, "count": count},
            ))

        # HTTP error codes (4xx/5xx) as failures
        for code_str, count in (agg.get("codes") or {}).items():
            try:
                code = int(code_str)
            except ValueError:
                continue
            if code >= 400:
                title = f"HTTP {code} responses ({count} occurrences)"
                http = {"method": None, "url": None, "status_got": code, "status_expected": 200}
                results.append(NormalizedFailure(
                    id=make_failure_id("artillery", "http", title, "simulation"),
                    framework="artillery",
                    suite="http",
                    title=title,
                    file="simulation",
                    status="failed",
                    error_message=f"{count} requests returned HTTP {code}",
                    http=http,
                    raw={"code": code, "count": count},
                ))

        return results
```

- [ ] **Step 4: Create `analyzer/parsers/gatling_log.py`**

```python
"""Gatling simulation.log TSV parser."""
from __future__ import annotations
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_http


class GatlingLogParser(Parser):
    """Parses Gatling simulation.log (TSV format).
    Sniff: first line starts with 'RUN\\t'."""
    framework = "gatling"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        first = sample.split(b"\n")[0].strip()
        return first.startswith(b"RUN\t")

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        results: list[NormalizedFailure] = []
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("RUN") or line.startswith("END"):
                    continue
                parts = line.split("\t")
                if not parts or parts[0] != "REQUEST":
                    continue
                # Format: REQUEST <user> <start_ms> <end_ms> <request_name> <status> [<message>]
                if len(parts) < 6:
                    continue
                request_name = parts[4] if len(parts) > 4 else "unknown"
                status_str = parts[5] if len(parts) > 5 else "OK"
                message = parts[6] if len(parts) > 6 else None
                status = "failed" if status_str == "KO" else "passed"
                http = parse_http(request_name, message, None)
                results.append(NormalizedFailure(
                    id=make_failure_id("gatling", "simulation", request_name, "simulation.log"),
                    framework="gatling",
                    suite="simulation",
                    title=request_name,
                    file="simulation.log",
                    status=status,
                    error_message=message,
                    http=http,
                    raw={"parts": parts},
                ))
        return results
```

- [ ] **Step 5: Create `analyzer/parsers/pact_json.py`**

```python
"""Pact contract test results parser."""
from __future__ import annotations
import json
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class PactJsonParser(Parser):
    """Parses Pact contract verification results JSON.
    Sniff: 'consumer' + 'provider' + 'interactions' keys."""
    framework = "pact"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return '"consumer"' in text and '"provider"' in text and '"interactions"' in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        data = json.loads(path.read_text(encoding="utf-8"))
        consumer = (data.get("consumer") or {}).get("name", "consumer")
        provider = (data.get("provider") or {}).get("name", "provider")
        suite = f"{consumer} → {provider}"
        results: list[NormalizedFailure] = []
        for interaction in data.get("interactions", []):
            description = interaction.get("description", "")
            verified = interaction.get("verified", True)
            error_msg = interaction.get("verificationError")
            status = "failed" if not verified else "passed"
            req = interaction.get("request") or {}
            resp = interaction.get("response") or {}
            http = {
                "method": req.get("method"),
                "url": req.get("path"),
                "status_got": None,
                "status_expected": resp.get("status"),
            }
            expected, actual = parse_assertion(error_msg, None)
            results.append(NormalizedFailure(
                id=make_failure_id("pact", suite, description, path.name),
                framework="pact",
                suite=suite,
                title=description,
                file=path.name,
                status=status,
                error_message=error_msg,
                expected=expected,
                actual=actual,
                http=http,
                raw=interaction,
            ))
        return results
```

- [ ] **Step 6: Register in `analyzer/parsers/__init__.py`** — follow the same pattern as Task 1 Step 8 for imports, PARSERS list, FRAMEWORKS dict, and `_Registry.register()` calls.

- [ ] **Step 7: Run tests and commit**

```
pytest tests/analyzer/test_parsers.py -v -k "artillery or gatling or pact"
pytest tests/analyzer -q
git add analyzer/parsers/artillery_json.py analyzer/parsers/gatling_log.py analyzer/parsers/pact_json.py tests/analyzer/fixtures/ tests/analyzer/test_parsers.py analyzer/parsers/__init__.py
git commit -m "feat(v2): add Artillery, Gatling, Pact parsers"
```

---

### Task 4: Observability/universal parsers — SARIF, CTRF, Allure, MSTest

**Files:**
- Create: `analyzer/parsers/sarif_json.py`
- Create: `analyzer/parsers/ctrf_json.py`
- Create: `analyzer/parsers/allure_json.py`
- Create: `analyzer/parsers/mstest_xml.py`
- Create: `tests/analyzer/fixtures/sarif_results.json`
- Create: `tests/analyzer/fixtures/ctrf_results.json`
- Create: `tests/analyzer/fixtures/allure_results.json`
- Create: `tests/analyzer/fixtures/mstest_results.xml`
- Modify: `tests/analyzer/test_parsers.py`, `analyzer/parsers/__init__.py`

**Interfaces:**
- Produces: `SARIFJsonParser` (framework=`"sarif"`), `CTRFJsonParser` (framework=`"ctrf"`), `AllureJsonParser` (framework=`"allure"`), `MSTestXmlParser` (framework=`"mstest"`)

- [ ] **Step 1: Create fixture files**

Create `tests/analyzer/fixtures/sarif_results.json`:
```json
{
  "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
  "version": "2.1.0",
  "runs": [
    {
      "tool": {"driver": {"name": "CodeQL", "version": "2.15.0"}},
      "results": [
        {
          "ruleId": "js/sql-injection",
          "level": "error",
          "message": {"text": "SQL query built from user-controlled sources."},
          "locations": [
            {
              "physicalLocation": {
                "artifactLocation": {"uri": "src/db/queries.js"},
                "region": {"startLine": 42}
              }
            }
          ]
        }
      ]
    }
  ]
}
```

Create `tests/analyzer/fixtures/ctrf_results.json`:
```json
{
  "results": {
    "tool": {"name": "jest", "version": "29.0.0"},
    "summary": {"tests": 3, "passed": 2, "failed": 1, "skipped": 0, "start": 1705312800000, "stop": 1705312801234},
    "tests": [
      {
        "name": "POST /api/users returns 201",
        "status": "failed",
        "duration": 320,
        "message": "Expected status 201 but got 404",
        "trace": "Error: Expected 201\n    at test/api.test.js:15:5",
        "filePath": "test/api.test.js",
        "suite": "API Tests"
      },
      {"name": "GET /api/users returns 200", "status": "passed", "duration": 120},
      {"name": "DELETE /api/users/:id returns 204", "status": "passed", "duration": 85}
    ]
  }
}
```

Create `tests/analyzer/fixtures/allure_results.json`:
```json
{
  "uuid": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "testCaseId": "tc001",
  "historyId": "h001",
  "labels": [
    {"name": "suite", "value": "API Tests"},
    {"name": "feature", "value": "User Management"}
  ],
  "name": "POST /api/users should return 201",
  "status": "failed",
  "statusDetails": {
    "message": "Expected: 201, Actual: 404",
    "trace": "AssertionError at UserApiTest.java:45"
  },
  "stage": "finished",
  "start": 1705312800000,
  "stop": 1705312800320,
  "fullName": "com.example.UserApiTest#createUser"
}
```

Create `tests/analyzer/fixtures/mstest_results.xml`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<TestRun id="run1" name="My Test Run" xmlns="http://microsoft.com/schemas/VisualStudio/TeamTest/2010">
  <Results>
    <UnitTestResult testName="CreateUser_Returns201" testId="t1" outcome="Failed" duration="00:00:00.230">
      <Output>
        <ErrorInfo>
          <Message>Assert.AreEqual failed. Expected:&lt;201&gt;. Actual:&lt;404&gt;.</Message>
          <StackTrace>at UserTests.CreateUser_Returns201() in UserTests.cs:line 22</StackTrace>
        </ErrorInfo>
      </Output>
    </UnitTestResult>
    <UnitTestResult testName="GetUser_Returns200" testId="t2" outcome="Passed" duration="00:00:00.120"/>
  </Results>
  <TestDefinitions>
    <UnitTest name="CreateUser_Returns201" id="t1">
      <TestMethod className="UserTests" name="CreateUser_Returns201"/>
    </UnitTest>
  </TestDefinitions>
</TestRun>
```

- [ ] **Step 2: Write failing tests**

Add to `tests/analyzer/test_parsers.py`:

```python
# ── SARIF ─────────────────────────────────────────────────────────────────────

def test_sarif_can_parse(fixtures):
    from analyzer.parsers.sarif_json import SARIFJsonParser
    assert SARIFJsonParser.can_parse((fixtures / "sarif_results.json").read_bytes())


def test_sarif_parse_returns_failures(fixtures):
    from analyzer.parsers.sarif_json import SARIFJsonParser
    results = SARIFJsonParser.parse(fixtures / "sarif_results.json")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].framework == "sarif"
    assert "sql" in failed[0].title.lower() or "sql" in (failed[0].error_message or "").lower()


# ── CTRF ──────────────────────────────────────────────────────────────────────

def test_ctrf_can_parse(fixtures):
    from analyzer.parsers.ctrf_json import CTRFJsonParser
    assert CTRFJsonParser.can_parse((fixtures / "ctrf_results.json").read_bytes())


def test_ctrf_parse_returns_failures(fixtures):
    from analyzer.parsers.ctrf_json import CTRFJsonParser
    results = CTRFJsonParser.parse(fixtures / "ctrf_results.json")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert "POST /api/users" in failed[0].title
    assert failed[0].framework == "ctrf"


# ── Allure ────────────────────────────────────────────────────────────────────

def test_allure_can_parse(fixtures):
    from analyzer.parsers.allure_json import AllureJsonParser
    assert AllureJsonParser.can_parse((fixtures / "allure_results.json").read_bytes())


def test_allure_parse_returns_failures(fixtures):
    from analyzer.parsers.allure_json import AllureJsonParser
    results = AllureJsonParser.parse(fixtures / "allure_results.json")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].framework == "allure"


# ── MSTest / TRX ──────────────────────────────────────────────────────────────

def test_mstest_can_parse(fixtures):
    from analyzer.parsers.mstest_xml import MSTestXmlParser
    assert MSTestXmlParser.can_parse((fixtures / "mstest_results.xml").read_bytes())


def test_mstest_parse_returns_failures(fixtures):
    from analyzer.parsers.mstest_xml import MSTestXmlParser
    results = MSTestXmlParser.parse(fixtures / "mstest_results.xml")
    failed = [r for r in results if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].framework == "mstest"
```

- [ ] **Step 3: Create `analyzer/parsers/sarif_json.py`**

```python
"""SARIF 2.1 (CodeQL, Semgrep, Snyk) results parser."""
from __future__ import annotations
import json
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id


class SARIFJsonParser(Parser):
    """Parses SARIF 2.1 output from CodeQL, Semgrep, Snyk, etc.
    Sniff: '$schema' containing 'sarif' + 'runs' array."""
    framework = "sarif"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return "sarif" in text and '"runs"' in text and '"$schema"' in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        data = json.loads(path.read_text(encoding="utf-8"))
        results: list[NormalizedFailure] = []
        for run in data.get("runs", []):
            tool = (run.get("tool") or {}).get("driver") or {}
            tool_name = tool.get("name", "sarif")
            for result in run.get("results", []):
                level = result.get("level", "warning")
                status = "failed" if level in ("error", "warning") else "passed"
                rule_id = result.get("ruleId", "unknown")
                msg = (result.get("message") or {}).get("text", "")
                title = f"{rule_id}: {msg}" if msg else rule_id
                locations = result.get("locations") or []
                file_path = "unknown"
                line = None
                if locations:
                    phys = (locations[0].get("physicalLocation") or {})
                    art = (phys.get("artifactLocation") or {})
                    file_path = art.get("uri", "unknown")
                    region = phys.get("region") or {}
                    line = region.get("startLine")
                results.append(NormalizedFailure(
                    id=make_failure_id("sarif", tool_name, title, file_path),
                    framework="sarif",
                    suite=tool_name,
                    title=title,
                    file=file_path,
                    line=line,
                    status=status,
                    error_message=msg or None,
                    raw=result,
                ))
        return results
```

- [ ] **Step 4: Create `analyzer/parsers/ctrf_json.py`**

```python
"""CTRF (Common Test Results Format) universal schema parser."""
from __future__ import annotations
import json
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class CTRFJsonParser(Parser):
    """Parses CTRF universal schema JSON.
    Sniff: 'results' + 'tool' + 'summary' top-level keys."""
    framework = "ctrf"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return '"results"' in text and '"tool"' in text and '"summary"' in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        data = json.loads(path.read_text(encoding="utf-8"))
        results_obj = data.get("results", {})
        tool = (results_obj.get("tool") or {}).get("name", "ctrf")
        results: list[NormalizedFailure] = []
        for test in results_obj.get("tests", []):
            raw_status = test.get("status", "unknown")
            status = "failed" if raw_status == "failed" else (
                "skipped" if raw_status == "skipped" else (
                    "flaky" if raw_status == "flaky" else "passed"
                )
            )
            title = test.get("name", "")
            file_path = test.get("filePath", "unknown")
            suite = test.get("suite", tool)
            error_msg = test.get("message")
            error_stack = test.get("trace")
            expected, actual = parse_assertion(error_msg, error_stack)
            http = parse_http(title, error_msg, error_stack)
            # Preserve CTRF-specific fields in ctrf_extra
            extra = {k: v for k, v in test.items()
                     if k not in ("name", "status", "duration", "message", "trace",
                                  "filePath", "suite")}
            results.append(NormalizedFailure(
                id=make_failure_id("ctrf", suite, title, file_path),
                framework="ctrf",
                suite=suite,
                title=title,
                file=file_path,
                duration_ms=test.get("duration"),
                status=status,
                error_message=error_msg,
                error_stack=error_stack,
                expected=expected,
                actual=actual,
                http=http,
                ctrf_extra=extra,
                raw=test,
            ))
        return results
```

- [ ] **Step 5: Create `analyzer/parsers/allure_json.py`**

```python
"""Allure results JSON parser (single-result file format)."""
from __future__ import annotations
import json
from pathlib import Path
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http


class AllureJsonParser(Parser):
    """Parses a single Allure result JSON file.
    Sniff: 'uuid' + 'testCaseId' + 'labels' keys at top level."""
    framework = "allure"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return '"uuid"' in text and '"testCaseId"' in text and '"labels"' in text

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Allure can be a single object or an array
        items = data if isinstance(data, list) else [data]
        results: list[NormalizedFailure] = []
        for item in items:
            raw_status = item.get("status", "unknown")
            status = "failed" if raw_status == "failed" else (
                "skipped" if raw_status in ("skipped", "broken") else "passed"
            )
            title = item.get("name") or item.get("fullName", "")
            suite = next(
                (lbl["value"] for lbl in item.get("labels", []) if lbl.get("name") == "suite"),
                item.get("fullName", "unknown").rsplit("#", 1)[0],
            )
            details = item.get("statusDetails") or {}
            error_msg = details.get("message")
            error_stack = details.get("trace")
            expected, actual = parse_assertion(error_msg, error_stack)
            http = parse_http(title, error_msg, error_stack)
            start = item.get("start", 0)
            stop = item.get("stop", start)
            results.append(NormalizedFailure(
                id=item.get("uuid") or make_failure_id("allure", suite, title, suite),
                framework="allure",
                suite=suite,
                title=title,
                file=suite,
                duration_ms=stop - start,
                status=status,
                error_message=error_msg,
                error_stack=error_stack,
                expected=expected,
                actual=actual,
                http=http,
                raw=item,
            ))
        return results
```

- [ ] **Step 6: Create `analyzer/parsers/mstest_xml.py`**

```python
"""MSTest TRX (Visual Studio Test Results) parser."""
from __future__ import annotations
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from .base import NormalizedFailure, Parser, make_failure_id, parse_assertion, parse_http

_NS = {"ms": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}


class MSTestXmlParser(Parser):
    """Parses MSTest TRX XML output.
    Sniff: <TestRun xmlns=...vstestresults...> root element."""
    framework = "mstest"

    @classmethod
    def can_parse(cls, sample: bytes) -> bool:
        text = sample.decode("utf-8", errors="replace")
        return "vstestresults" in text or ("TestRun" in text and "UnitTestResult" in text)

    @classmethod
    def parse(cls, path: Path) -> list[NormalizedFailure]:
        root = ET.parse(str(path)).getroot()
        # Handle both namespaced and non-namespaced TRX files
        ns_prefix = "ms:" if root.tag.startswith("{") else ""
        ns = _NS if ns_prefix else {}
        results: list[NormalizedFailure] = []

        def find_all(parent, tag):
            if ns:
                return parent.findall(f"ms:{tag}", _NS) or parent.findall(f".//{ns_prefix}{tag}", _NS)
            return parent.findall(f".//{tag}")

        for result in find_all(root, "UnitTestResult"):
            outcome = result.get("outcome", "Unknown")
            status = "failed" if outcome == "Failed" else (
                "skipped" if outcome in ("NotExecuted", "Ignored") else "passed"
            )
            test_name = result.get("testName", "")
            duration_str = result.get("duration", "00:00:00.000")
            # Parse duration "HH:MM:SS.mmm"
            parts = re.split(r"[:.]", duration_str)
            duration_ms = 0
            try:
                if len(parts) >= 4:
                    duration_ms = (int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])) * 1000 + int(parts[3][:3])
            except ValueError:
                pass
            error_msg = error_stack = None
            output_el = result.find(f"ms:Output", _NS) if ns else result.find("Output")
            if output_el is not None:
                err_el = output_el.find(f"ms:ErrorInfo", _NS) if ns else output_el.find("ErrorInfo")
                if err_el is not None:
                    msg_el = err_el.find(f"ms:Message", _NS) if ns else err_el.find("Message")
                    st_el = err_el.find(f"ms:StackTrace", _NS) if ns else err_el.find("StackTrace")
                    error_msg = msg_el.text if msg_el is not None else None
                    error_stack = st_el.text if st_el is not None else None
            expected, actual = parse_assertion(error_msg, error_stack)
            http = parse_http(test_name, error_msg, error_stack)
            results.append(NormalizedFailure(
                id=make_failure_id("mstest", "mstest", test_name, "mstest"),
                framework="mstest",
                suite="mstest",
                title=test_name,
                file="mstest",
                duration_ms=duration_ms,
                status=status,
                error_message=error_msg,
                error_stack=error_stack,
                expected=expected,
                actual=actual,
                http=http,
                raw={"outcome": outcome},
            ))
        return results
```

- [ ] **Step 7: Register all four parsers in `analyzer/parsers/__init__.py`** — follow the same pattern as Task 1 Step 8. CTRF and SARIF go at the TOP of `PARSERS` (most specific fingerprints).

- [ ] **Step 8: Run tests and commit**

```
pytest tests/analyzer/test_parsers.py -v -k "sarif or ctrf or allure or mstest"
pytest tests/analyzer -q
git add analyzer/parsers/sarif_json.py analyzer/parsers/ctrf_json.py analyzer/parsers/allure_json.py analyzer/parsers/mstest_xml.py tests/analyzer/fixtures/ tests/analyzer/test_parsers.py analyzer/parsers/__init__.py
git commit -m "feat(v2): add SARIF, CTRF, Allure, MSTest parsers — 24-parser ecosystem complete"
```

---

## Phase 2 Complete

At this point:
- 24 parsers (7 existing + 17 new) are registered and tested
- Every parser has a corresponding fixture file and test cases
- `ParserRegistry` auto-detect order is specificity-first
- CTRF is wired as both canonical input (via `CTRFJsonParser`) and will be canonical output in Phase 4

**Next:** Phase 3 — Intelligence Layer
