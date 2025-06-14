Okay, this is an excellent find. The Cloud Build was successful, but now we're seeing an error in the *actual Cloud Run instance logs*. This is a different environment, and it has revealed the next issue.

This is a very common and logical problem to encounter at this stage.

### Error Analysis

Let's look at the specific error message from your Cloud Run log:

```
File "/home/main.py", line 54, in <module>
    raise ValueError(
ValueError: 无法在 TWS 安装日志中找到版本号。 期望的模式是 'IB Gateway ([0-9]{3})'。 日志文件 '/root/Jts/tws_install.log' 的内容是: 'Unpacking JRE ...'
```

**What this error means:**
1.  Your `main.py` file is trying to open and read the file at `/root/Jts/tws_install.log`.
2.  It's reading the content, which is `'Unpacking JRE ...'`.
3.  It's then trying to find the pattern `IB Gateway XXX` (where XXX is a 3-digit number) inside that content.
4.  It cannot find the pattern, so the `re.search(...)` returns `None`.
5.  Your new, robust code correctly catches this `None` and raises the `ValueError` with a very clear message, telling us exactly what's wrong.

**The Root Cause:**
The problem is a difference between your **build-time environment** and your **run-time environment**.

*   **During Cloud Build (Integration Test):** You correctly set the `MOCK_TWS_VERSION=981` environment variable. Your code in `main.py` (when run as part of the test) *should have used this mock version*. It seems it didn't, which is a separate small issue, but let's focus on the main problem.

*   **During Cloud Run (Actual Execution):** When your container starts in the Cloud Run service, there is **no `MOCK_TWS_VERSION` environment variable set**. Therefore, your code falls back to the second option: trying to parse the `tws_install.log` file. This file is created by the `ib-gateway` installer inside your *base image*, but its content (`Unpacking JRE ...`) doesn't contain the version number in the format you expect.

### The Solution: Environment Variable Mismatch

The simplest and most robust solution is to stop relying on parsing a log file at runtime. The version of IB Gateway is a static part of your base image. We should treat it as a build-time constant and pass it into the runtime environment.

We need to do two things:
1.  Fix `main.py` to correctly prioritize the environment variable.
2.  Update the `cloudbuild.yaml` deployment step to pass this version number as an environment variable to the final Cloud Run service.

---

### Action Plan

#### Step 1: Fix `main.py` to Prioritize the Mock Version

Your current code in `main.py` still tries to parse the log file regardless of whether `MOCK_TWS_VERSION` exists. Let's fix that.

**Open `main.py` and find this block:**
```python
# --- This is your current code block ---
# 1. 首先读取日志文件内容
with open(TWS_INSTALL_LOG, 'r') as fp:
    install_log = fp.read()

# 2. 执行正则表达式搜索，并将结果保存在一个变量中
match = re.search('IB Gateway ([0-9]{3})', install_log)

# 3. 检查搜索是否成功...
if not match:
    raise ValueError(
        f"无法在 TWS 安装日志中找到版本号。 "
        # ...
    )

# 4. 只有在搜索成功后，才提取版本号
tws_version = match.group(1)
```

**Replace it with this corrected logic:**
```python
# --- Corrected logic for main.py ---
# First, try to get the version from an environment variable.
# This is the most reliable method for both testing and production.
tws_version = environ.get('TWS_VERSION')

# If the environment variable is not set, then fall back to parsing the log file.
if not tws_version:
    try:
        with open(TWS_INSTALL_LOG, 'r') as fp:
            install_log = fp.read()
        
        match = re.search('IB Gateway ([0-9]{3})', install_log)
        
        if not match:
            raise ValueError(
                f"TWS_VERSION env var not set AND could not find version in log file. "
                f"Expected pattern 'IB Gateway ([0-9]{3})' in '{TWS_INSTALL_LOG}'. "
                f"Log content: '{install_log}'"
            )
        tws_version = match.group(1)
        logging.info(f"Extracted TWS version '{tws_version}' from log file.")

    except FileNotFoundError:
        raise FileNotFoundError(
            f"TWS_VERSION env var not set AND install log file not found at '{TWS_INSTALL_LOG}'"
        )
else:
    logging.info(f"Using TWS version '{tws_version}' from environment variable.")

# Now, tws_version is guaranteed to be set if we reach this point.
ibc_config = {
    'gateway': True,
    'twsVersion': tws_version, # Use the safely acquired version
    **env
}
# --- End of corrected logic ---
```
This new logic is much better: it prioritizes a clean environment variable (`TWS_VERSION`) and only attempts the fragile file-parsing as a last resort.

#### Step 2: Update `cloudbuild.yaml` to Set the Environment Variable

Now, we need to tell Cloud Run to set the `TWS_VERSION` environment variable when it starts your container.

**Open `cloud-run/application/cloudbuild.yaml` and find the `deploy new revision` step.**

It currently looks like this:
```yaml
# deploy new revision
- name: 'gcr.io/cloud-builders/gcloud-slim'
  args:
  - "run"
  - "deploy"
  - "ib-${_TRADING_MODE}"
  # ... other args ...
  - "--update-env-vars"
  - "PROJECT_ID=${PROJECT_ID},TRADING_MODE=${_TRADING_MODE}"
```

**Modify the `--update-env-vars` line** to include the TWS version. We'll hardcode it to `981` since that's what your base image uses.

**The corrected step:**
```yaml
#### deploy new revision
- name: 'gcr.io/cloud-builders/gcloud-slim'
  args:
  - "run"
  - "deploy"
  - "ib-${_TRADING_MODE}"
  # ... other args ...
  - "--update-env-vars"
  # Add TWS_VERSION here
  - "PROJECT_ID=${PROJECT_ID},TRADING_MODE=${_TRADING_MODE},TWS_VERSION=981" 
```

### Summary of What To Do

1.  **Update `main.py`:** Replace the TWS version extraction logic with the new, improved version from "Step 1" above.
2.  **Update `cloudbuild.yaml`:** Add `TWS_VERSION=981` to the `--update-env-vars` flag in the final deployment step, as shown in "Step 2".
3.  **Commit and Redeploy:** Save both files, commit them to git, and run your `gcloud builds submit` command again.

This will fix the startup error. The Cloud Run service will now receive the TWS version directly as an environment variable, avoiding the need to parse the log file at runtime.