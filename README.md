# FishingBucket

---

<div style="text-align: center">

![GitHub commit activity](https://img.shields.io/github/commit-activity/m/FishingBucket/FishingBucket)
![GitHub contributors](https://img.shields.io/github/contributors/FishingBucket/FishingBucket)
![GitHub License](https://img.shields.io/github/license/FishingBucket/FishingBucket)
![GitHub repo size](https://img.shields.io/github/repo-size/FishingBucket/FishingBucket)

</div>

<div style="text-align: center">

![Fluxer](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fapi.fluxer.app%2Fv1%2Finvites%2Ffishingbucket&query=%24.presence_count&suffix=%20online&logo=Fluxer&label=Fluxer&logoColor=4641D9&labelColor=white&color)
![Discord](https://img.shields.io/discord/1478257699274621120?label=Discord&logo=discord&labelColor=white)

</div>

FishingBucket is the next-generation of proxy services.

Fluxer and Discord bot to forward messages into faux-profiles called "proxies", akin to
Tupperbox and PluralKit.


## Self-Hosting

To self-host FishingBucket, ensure that you have [Python 14](https://www.python.org/downloads/) installed.
Furthermore, obtain either [uv](https://docs.astral.sh/uv/) or [pip](https://pypi.org/project/pip/) for
dependency management.

To get started with self-hosting, make a virtual environment and install the dependencies of the bot at the project root:

- With `pip`:
  ```shell
  pip install -e .
  ```
- With `uv`:
  ```shell
  uv sync
  ```

After the packages are installed, run the self-hosting wizard in the project root:

- With `python` and venv:
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
