from os import environ
from pathlib import Path
from tempfile import TemporaryDirectory

from dulwich import porcelain
from dulwich.repo import Repo
from urllib3 import ProxyManager

## Configuration settings:
# Source url of the repo (Note: https here. ssh would work as well, a bit differently).
GITURL = "https://github.com/lomignet/thisdataguy_snippets"
# Gihthub token: https://docs.github.com/en/github/authenticating-to-github/creating-a-personal-access-token
TOKEN = "12345blah"
## /end of configuration.

# If the environment variable https_proxy exists, we need to tell Dulwich to use a proxy.
if environ.get("https_proxy", None):
    pool_manager = ProxyManager(environ["https_proxy"], num_pools=1)
else:
    pool_manager = None

with TemporaryDirectory() as gitrootdir:

    # Gotta love operator overloading!
    gitdir = Path(gitrootdir) / "repo"
    print("Cloning...")
    repo = porcelain.clone(
        GITURL,
        password=TOKEN,
        # Tokens are kinda public keys, no need for a username but it still needs to be provided for Dulwich.
        username="not relevant",
        target=gitdir,
        checkout=True,
        pool_manager=pool_manager,
    )
    print("Cloned.")

    # Do something clever with the files in the repo, for instance create an empty readme.
    readme = gitdir / "readme.md"
    readme.touch()
    porcelain.add(repo, readme)

    print("Committing...")
    porcelain.commit(repo, "Empty readme added.")
    print("Commited.")

    print("Pushing...")
    porcelain.push(
        repo,
        remote_location=GITURL,
        refspecs="master", # branch to push to
        password=TOKEN,
        # Token are kinda public keys, no need for a username but it still needs to be provided for Dulwich.
        username="not relevant",
        pool_manager=pool_manager,
    )
    # Note: Dulwich 0.20.5 raised an exception here. It could be ignored but it was dirty:
    # File ".../venv/lib/python3.7/site-packages/dulwich/porcelain.py", line 996, in push
    #     (ref, error.encode(err_encoding)))
    # AttributeError: 'NoneType' object has no attribute 'encode'
    # Dulwich 0.20.6 fixed it.
    print("Pushed.")
