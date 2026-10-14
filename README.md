# FishingBucket

![GitHub commit activity](https://img.shields.io/github/commit-activity/m/FishingBucket/FishingBucket)
![GitHub contributors](https://img.shields.io/github/contributors/FishingBucket/FishingBucket)
![GitHub License](https://img.shields.io/github/license/FishingBucket/FishingBucket)
![GitHub repo size](https://img.shields.io/github/repo-size/FishingBucket/FishingBucket)

![Fluxer](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fapi.fluxer.app%2Fv1%2Finvites%2Ffishingbucket&query=%24.presence_count&suffix=%20online&logo=Fluxer&label=Fluxer&logoColor=4641D9&labelColor=white&color)
![Discord](https://img.shields.io/discord/1478257699274621120?label=Discord&logo=discord&labelColor=white)

---

FishingBucket is the next-generation of proxy services.

Fluxer and Discord bot to forward messages into faux-profiles called "proxies", akin to
Tupperbox and PluralKit.


# Documentation

User-facing documentation is coming soon!


# Self-Hosting

There are two ways to self-host FishingBucket: the first way is through running the raw Python source, and the second way
is running on Docker.

## From Source

To self-host FishingBucket from source, ensure that you have [Python 3.14](https://www.python.org/downloads/) installed.
Furthermore, obtain either [uv](https://docs.astral.sh/uv/) or [pip](https://pypi.org/project/pip/) for dependency management. [Git](https://git-scm.com/)
should also be installed to fetch the repository and the source code.

### Obtaining Source Code

To fetch the source code, execute the command in the parent directory of where you want to store your copy
of FishingBucket:

1. Clone the repository into the subdirectory `FishingBucket/`
   ```shell
   git clone --recurse-submodules https://github.com/FishingBucket/FishingBucket
   ```
2. Change current working directory into project root
   ```shell
   cd FishingBucket
   ```

Now, you should be able to move onto setting up your instance.

### Setup

To start setting up the instance, make a virtual environment and install the dependencies of the bot at the project root:

- With `pip`:
  - Windows:
    ```shell
    python -m venv .venv
    .venv\Scripts\activate
    python -m pip install -e .
    ```
  - Unix or macOS:
    ```shell
    python -m venv .venv
    source .venv/bin/activate
    python -m pip install -e .
    ```
- With `uv`:
  ```shell
  uv sync
  ```

After the packages are installed, run the self-hosting wizard in the project root:

- With `python` and inside venv:
  ```shell
  python scripts/initialize.py wizard
  ```
- With `uv`:
  ```shell
  uv run scripts/initialize.py wizard
  ```

After the scripts finish, the setup and configurations will be good to go. What's left is to run the actual bot itself:

- With `python` and venv:
  ```shell
  python main.py path/to/config.json
  ```
- With `uv`:
  ```shell
  uv run main.py path/to/config.json
  ```

### Updating Code

To update the source code for FishingBucket, make sure that you stopped your current copy of FishingBucket, then, run the
following commands in the project root:

1. Update source code:
   ```shell
   git pull --recurse-submodules
   ```
2. Update dependencies:
   - With `pip` and inside venv:
     ```shell
     python -m pip install -e .
     ```
   - With `uv`:
     ```shell
     uv sync
     ```
3. Run redownload script:
   - With `python` and inside venv:
     ```shell
     python scripts/initialize.py redownload
     ```
   - With `uv`:
     ```shell
     uv run scripts/initialize.py redownload
     ```

## Docker

Docker support is coming to FishingBucket soon! Keep your eyes peeled and watch the repository for updates!
