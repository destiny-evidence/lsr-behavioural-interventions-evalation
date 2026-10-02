# living-review-interventions

## Getting started

Install dependencies and set up the development environment

```
uv sync
uv add -e .
```

## [OPTIONAL] Secrets management

We use [fnox](https://fnox.jdx.dev/) to share encrypted secrets in git. 
Access is shared by adding public keys to `fnox.toml`, and then re-encrypting secrets (which can only be done by someone containing a key the secrets were encrypted with).

Install fnox
```sh
brew install fnox
```

or 

```sh
curl -sSL https://github.com/jdx/fnox/releases/latest/download/fnox-x86_64-unknown-linux-musl.tar.gz | tar xz
mv fnox ~/.local/bin/ && chmod +x ~/.local/bin/fnox
```

Make sure your key is in recipients in `fnox.toml`, (by submitting a PR) and 
if your key is in an exotic location, you will need to override key_file in `fnox.local.toml` 

## Syncing data

To pull data from the remote data-versioned store

If you are using fnox, simply prepend any dvc command with `fnox exec --`, and 
fnox will inject decrypted secrets into environment variables before running the command.

```sh
fnox exec -- uv run dvc pull
```

Otherwise, you will have to ask a maintainer for a key.

Once you have this, you can store this locally by running
```sh
uv run dvc remote modify --local azure sas_token 'YOUR_KEY_GOES_HERE'
```

Then you can sync data by running
```sh
uv run dvc pull
```


To commit changes to the data
```sh
uv run dvc add data # "stage" changes to the data
git add data.dvc # add this record of changes to git
git commit -m "new data" # git commit - this version of data will be associated with this commit
uv run dvc push # Push data version to remote azure storage
git push
```

## Development

Run code quality checks before committing:

```
uvx prek run --all-files
```