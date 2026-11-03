import csv
import io

from app.models import CSV_COLUMNS


def test_country_city_filters_groups_and_export_share_one_contract(client):
    login = client.post("/auth/dev-login", json={"email": "location-filter-contract@jobgrid.test"})
    assert login.status_code == 200

    # Use the raw Serper column names to verify the classic upload aliases.
    content = (
        "url,title,location_group,country,city,job_location\n"
        "https://locations.example/us-ny,Engineer A,remote,United States,New York City,New York\n"
        'https://locations.example/multi,Engineer B,hybrid,"Canada; United States","New York City; Austin",Multiple offices\n'
        "https://locations.example/ca,Engineer C,onsite,Canada,Toronto,Toronto\n"
        "https://locations.example/in,Engineer D,remote,India,Bengaluru,Bengaluru\n"
        "https://locations.example/us-york,Engineer E,onsite,United States,York,York\n"
        "https://locations.example/unknown,Engineer F,remote,,,Not stated\n"
    )
    uploaded = client.post(
        "/upload",
        files={"file": ("serper-locations.csv", content.encode(), "text/csv")},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["inserted"] == 6
    assert "country" not in uploaded.json()["unknown_extra_columns"]
    assert "city" not in uploaded.json()["unknown_extra_columns"]

    all_rows = client.get("/rows", params={"page_size": 100})
    assert all_rows.status_code == 200
    assert "location_country" in all_rows.json()["columns"]
    assert "location_city" in all_rows.json()["columns"]
    options = all_rows.json()["filter_options"]
    assert {"Canada", "United States", "India"} <= set(options["location_countries"])
    assert {"New York City", "Austin", "Toronto", "Bengaluru"} <= set(options["location_cities"])
    assert "Canada; United States" not in options["location_countries"]
    assert "New York City; Austin" not in options["location_cities"]

    usa = client.get("/rows", params={"location_country": "uNiTeD sTaTeS"})
    assert usa.status_code == 200
    assert {row["data"]["url"].split("/")[-1] for row in usa.json()["rows"]} == {"us-ny", "multi", "us-york"}

    ny = client.get("/rows", params={"location_city": "new york city"})
    assert ny.status_code == 200
    assert {row["data"]["url"].split("/")[-1] for row in ny.json()["rows"]} == {"us-ny", "multi"}

    assert client.get("/rows", params={"location_city": "york"}).json()["total_count"] == 1

    selected = client.get("/rows", params={
        "location_country": "United States",
        "location_city": "New York City",
        "location_group": "remote",
    })
    assert selected.status_code == 200
    assert [row["data"]["title"] for row in selected.json()["rows"]] == ["Engineer A"]

    for field, expected in (
        ("location_country", {"united states": 2, "canada; united states": 1, "canada": 1, "india": 1, "": 1}),
        ("location_city", {"new york city": 1, "new york city; austin": 1, "toronto": 1, "bengaluru": 1, "york": 1, "": 1}),
    ):
        grouped = client.get("/rows", params={"group_by": field, "page_size": 100})
        assert grouped.status_code == 200
        assert grouped.json()["group_counts"] == expected
        assert sum(grouped.json()["group_counts"].values()) == grouped.json()["total_count"] == 6

    filtered = {
        "location_country": "United States",
        "location_city": "New York City",
    }
    listed = client.get("/rows", params={**filtered, "page_size": 100}).json()
    exported = client.get("/crm/export/dashboard", params={
        **filtered, "format": "json", "scope": "filtered",
    })
    assert exported.status_code == 200, exported.text
    assert {row["url"] for row in exported.json()} == {
        row["data"]["url"] for row in listed["rows"]
    }
    assert len(exported.json()) == 2

    exported_csv = client.get("/crm/export/dashboard", params={
        **filtered, "format": "csv", "scope": "filtered",
    })
    assert exported_csv.status_code == 200
    reader = csv.DictReader(io.StringIO(exported_csv.text))
    assert set(CSV_COLUMNS).issubset(set(reader.fieldnames))
    assert len(list(reader)) == 2
