"""
SECBrain Watcher

Runtime Manager
"""


import os
from pathlib import Path

from connectors.vault_connector import VaultConnector
from connectors.git_connector import GitConnector
from connectors.ollama_connector import OllamaConnector



class RuntimeManager:


    def __init__(self):

        project_root = Path(__file__).resolve().parents[3]

        vault_path = os.environ.get(

            "SECBRAIN_VAULT_PATH",

            "/home/secbrain/Dokumente/SecBrain",

        )

        repository_path = os.environ.get(

            "SECBRAIN_WATCHER_REPOSITORY",

            str(project_root),

        )

        self.vault = VaultConnector(

            vault_path

        )


        self.git = GitConnector(repository_path)

        ollama_url = os.environ.get(

            "SECBRAIN_OLLAMA_URL",

            "http://127.0.0.1:11434",

        )

        self.ollama = OllamaConnector(ollama_url)

        observer_model = os.environ.get("SECBRAIN_OBSERVER_MODEL", "").strip()
        if observer_model:
            self.ollama.configure({"model": observer_model})



    def status(self):


        return {

            "vault":
            self.vault.scan(),


            "architecture":
            self.git.scan(),


            "ollama":
            self.ollama.scan()

        }
