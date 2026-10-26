import json
import os
from pathlib import Path
from typing import Any
import subprocess


class DataReader:
    def __init__(self, data_directory: str | Path):
        self.data_directory = Path(data_directory)
        self.loaded_files: dict[str, Any] = {}
        self.load_data()

    def load_data_directory(self, directory: Path, relative: str):
        for file in os.listdir(directory):
            if os.path.isdir(directory / file):
                self.load_data_directory(directory / file, relative + file + "/")
            else:
                with open(directory / file) as f:
                    if file.endswith(".json"):
                        self.loaded_files[relative + file] = json.loads(f.read())
                    else:
                        self.loaded_files[relative + file] = f.read()

    def load_data(self):
        self.loaded_files = {}
        self.load_data_directory(self.data_directory, "")
        self.load_extra()

    def __getitem__(self, item: str) -> Any:
        if item in self.loaded_files:
            return self.loaded_files[item]
        raise KeyError(f"Data file {item!r} is not found. Data directory is configured to {self.data_directory!r}.")


    def load_extra(self):
        # git hash
        try:
            commit_hash = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
            ).strip().decode("utf-8")
        except subprocess.CalledProcessError:
            commit_hash = "unknown"
        self.loaded_files["last_commit"] = commit_hash
