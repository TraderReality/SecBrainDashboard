"""
SECBrain Watcher

Vault Runtime Connector
"""


from pathlib import Path



class VaultConnector:


    def __init__(self, path):

        self.path = Path(path)



    def scan(self):

        if not self.path.exists():

            return {

                "status":"MISSING",
                "files":0,
                "markdown":0

            }


        files = list(
            self.path.rglob("*")
        )


        markdown = [

            f for f in files

            if f.suffix.lower() == ".md"

        ]


        return {

            "status":"READY",

            "path":str(self.path),

            "files":len(files),

            "markdown":len(markdown)

        }
