"""Language-specific remediation template selector."""
from __future__ import annotations

_FRAMEWORK_LANGUAGE: dict[str, str] = {
    "playwright": "js", "cypress": "js", "jest": "js", "vitest": "js",
    "mocha": "js", "wdio": "js", "detox": "js",
    "pytest": "python", "robot": "python",
    "go": "go",
    "junit": "jvm", "rest-assured": "jvm", "karate": "jvm", "testng": "jvm",
    "nunit": "dotnet", "xunit": "dotnet", "mstest": "dotnet",
    "rspec": "ruby", "phpunit": "php",
    "k6": "load", "artillery": "load", "gatling": "load",
    "newman": "api", "pact": "api",
}

_INSTALL_PREFIX: dict[str, str] = {
    "js": "npm install / npx",
    "python": "pip install / pytest",
    "go": "go test / go mod tidy",
    "jvm": "mvn test / gradle test",
    "dotnet": "dotnet test",
    "ruby": "bundle exec rspec",
    "php": "./vendor/bin/phpunit",
    "load": "check thresholds and SLA config",
    "api": "check endpoint URL and auth token",
}

_RUN_COMMAND: dict[str, str] = {
    "playwright": "npx playwright test --debug",
    "cypress": "npx cypress run --headed",
    "jest": "npx jest --verbose",
    "vitest": "npx vitest run --reporter verbose",
    "pytest": "pytest -s -v",
    "robot": "robot --loglevel DEBUG",
    "go": "go test -v -run TestName ./...",
    "junit": "mvn test -Dtest=ClassName#methodName",
    "nunit": "dotnet test --filter FullyQualifiedName~MethodName",
    "xunit": "dotnet test --filter Method=MethodName",
    "rspec": "bundle exec rspec spec/path_to_spec.rb",
    "phpunit": "./vendor/bin/phpunit --filter methodName",
    "k6": "k6 run --verbose script.js",
    "newman": "newman run collection.json --verbose",
}


def language_for_framework(framework: str) -> str:
    return _FRAMEWORK_LANGUAGE.get(framework.lower(), "unknown")


def run_command_for_framework(framework: str) -> str | None:
    return _RUN_COMMAND.get(framework.lower())


def install_prefix_for_language(language: str) -> str:
    return _INSTALL_PREFIX.get(language, "check your test runner")
