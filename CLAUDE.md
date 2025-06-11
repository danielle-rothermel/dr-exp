# dr_exp - Deep Learning Experiment Manager

## 📦 DEPENDENCY MANAGEMENT

### ⚠️ CRITICAL: Always Use `uv add`, Never `uv pip install`

This project uses `uv` for dependency management with a `pyproject.toml` file. Dependencies MUST be added using `uv add` to ensure they are properly tracked in both `pyproject.toml` and `uv.lock`.

**✅ CORRECT - Use these commands:**
```bash
# Add a production dependency
uv add package-name

# Add a development dependency
uv add --dev package-name

# Add with version constraints
uv add "package-name>=1.2.0"

# Add from git
uv add "package-name @ git+https://github.com/user/repo"

# Remove a dependency
uv remove package-name
```

**❌ INCORRECT - Never use these:**
```bash
# NEVER use uv pip install
uv pip install package-name  # ❌ Wrong!

# NEVER use pip directly
pip install package-name     # ❌ Wrong!
```

### Why This Matters
- `uv add` updates both `pyproject.toml` and `uv.lock` files
- `uv pip install` only installs to the environment without updating project files
- Using `uv pip install` breaks reproducibility and dependency tracking
- Team members won't get your dependencies if you use `uv pip install`

### Local Development Dependencies
For temporary local testing of editable packages:
```bash
# Only for temporary local development - not for permanent dependencies!
uv pip install -e ../local-package

# When done testing, add properly:
uv add "package @ git+https://github.com/user/repo"
```
