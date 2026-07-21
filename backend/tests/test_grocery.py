"""Grocery lists: parent-only writes, store scoping, General-list fallback."""


def add_item(client, title, list_id=None):
    res = client.post("/grocery", json={"title": title, "list_id": list_id})
    assert res.status_code == 201, res.text
    return res.json()


def add_store(client, name):
    res = client.post("/grocery/lists", json={"name": name})
    assert res.status_code == 201, res.text
    return res.json()


def test_everyone_can_read_only_parents_can_write(owner, child):
    item = add_item(owner, "Milk")
    store = add_store(owner, "Walmart")

    # The child sees everything...
    state = child.get("/grocery").json()
    assert [lst["name"] for lst in state["lists"]] == ["Walmart"]
    assert [i["title"] for i in state["items"]] == ["Milk"]

    # ...and can change nothing.
    assert child.post("/grocery", json={"title": "Candy"}).status_code == 403
    assert child.patch(f"/grocery/{item['id']}", json={"checked": True}).status_code == 403
    assert child.delete(f"/grocery/{item['id']}").status_code == 403
    assert child.post("/grocery/clear-checked").status_code == 403
    assert child.post("/grocery/lists", json={"name": "Target"}).status_code == 403
    assert child.delete(f"/grocery/lists/{store['id']}").status_code == 403


def test_anon_gets_401(anon):
    assert anon.get("/grocery").status_code == 401


def test_duplicate_store_names_rejected_case_insensitively(owner):
    add_store(owner, "Walmart")
    res = owner.post("/grocery/lists", json={"name": "walmart"})
    assert res.status_code == 400


def test_clear_checked_only_touches_one_list(owner):
    walmart = add_store(owner, "Walmart")
    safeway = add_store(owner, "Safeway")
    w_item = add_item(owner, "Dog food", walmart["id"])
    s_item = add_item(owner, "Salmon", safeway["id"])
    g_item = add_item(owner, "Batteries")  # General

    for item in (w_item, s_item, g_item):
        owner.patch(f"/grocery/{item['id']}", json={"checked": True})

    # Clearing Walmart must leave Safeway's and General's checked items alone.
    state = owner.post(f"/grocery/clear-checked?list_id={walmart['id']}").json()
    titles = [i["title"] for i in state["items"]]
    assert "Dog food" not in titles
    assert "Salmon" in titles and "Batteries" in titles

    # Clearing General (no list_id) leaves Safeway's item alone.
    state = owner.post("/grocery/clear-checked").json()
    titles = [i["title"] for i in state["items"]]
    assert titles == ["Salmon"]


def test_removing_a_store_moves_items_to_general(owner):
    store = add_store(owner, "Costco")
    item = add_item(owner, "Dog treats", store["id"])
    assert item["list_id"] == store["id"]

    assert owner.delete(f"/grocery/lists/{store['id']}").status_code == 204
    state = owner.get("/grocery").json()
    assert state["lists"] == []
    survivor = next(i for i in state["items"] if i["title"] == "Dog treats")
    assert survivor["list_id"] is None  # fell back to General, not deleted


def test_unknown_store_rejected(owner):
    assert owner.post("/grocery", json={"title": "Ghost", "list_id": 99}).status_code == 400
    assert owner.post("/grocery/clear-checked?list_id=99").status_code == 400


def test_moving_an_item_between_lists(owner):
    store = add_store(owner, "Safeway")
    item = add_item(owner, "Salmon")  # starts on General
    moved = owner.patch(f"/grocery/{item['id']}", json={"list_id": store["id"]}).json()
    assert moved["list_id"] == store["id"]
    back = owner.patch(f"/grocery/{item['id']}", json={"list_id": None}).json()
    assert back["list_id"] is None
