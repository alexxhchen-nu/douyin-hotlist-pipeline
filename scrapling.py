import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo

    return


app._unparsable_cell(
    r"""
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

    """,
    name="_"
)


if __name__ == "__main__":
    app.run()
