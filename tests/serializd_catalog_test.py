"""WAYMARK Serializd catalog search test.

Read-only test for the authenticated Serializd catalog-search endpoint.
"""

from serializd import search_catalog


def main():
    print("WAYMARK Serializd catalog search test")
    query = input("Title to search on Serializd: ").strip()

    if not query:
        raise SystemExit("No title entered.")

    try:
        results = search_catalog(query)
    except Exception as exc:
        print(f"Catalog search failed: {type(exc).__name__}: {exc}")
        raise SystemExit(1)

    print(f"Catalog matches found: {len(results)}")

    for index, result in enumerate(results[:10], 1):
        print(
            f"{index}. {result.get('name', 'Unknown')} "
            f"| Serializd ID: {result.get('id', 'Unknown')} "
            f"| First air date: {result.get('firstAirDate', 'Unknown')}"
        )


if __name__ == "__main__":
    main()
