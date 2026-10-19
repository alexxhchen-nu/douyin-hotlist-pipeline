import marimo as mo

__generated_with = "0.25.1"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    return (mo,)

@app.cell
def _(mo):
    !pip install scrapling
    !pip install scrapling[all]
    return (mo,)


@app.cell
def _(mo):
    mo.md(r"""
    # Setting Up Scrapling

    Scrapling is an adaptive web scraping library for Python. Follow the steps below to get it installed and ready to use.

    ## 1. Prerequisites

    - Python 3.9 or newer
    - `pip` (comes bundled with Python)

    ## 2. Create a virtual environment (recommended)

    ```bash
    python -m venv scrapling-env
    source scrapling-env/bin/activate      # macOS / Linux
    scrapling-env\Scripts\activate         # Windows
    ```

    ## 3. Install Scrapling

    Basic installation:

    ```bash
    pip install scrapling
    ```

    For the full feature set (Stealthy fetcher, Playwright support, adblocker, etc.):

    ```bash
    pip install scrapling[all]
    ```

    You can also install only what you need, for example:

    ```bash
    pip install scrapling[stealthy]        # Stealthy fetcher support
    pip install scrapling[playwright]      # Playwright browser support
    ```

    ## 4. Verify the installation

    ```python
    from scrapling import Fetcher
    print("Scrapling is ready!")
    ```

    ## 5. First use

    Fetch and parse a page with the adaptive engine:

    ```python
    from scrapling import Fetcher

    page = Fetcher.get("https://example.com")
    print(page.css("h1").text)      # CSS selectors
    print(page.xpath("//h1").text)  # XPath also works
    ```

    You're all set — Scrapling is ready to use in your project.
    """)
    return


if __name__ == "__main__":
    app.run()
