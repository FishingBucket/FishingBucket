import json

type JSONPrimitive = str | int | float | bool | None | list[JSONPrimitive] | dict[str, JSONPrimitive]
type Path = list[str | int]

def represent_path(path: Path) -> str:
    return "~/" + "/".join(str(p) for p in path)

def without_element(lst: list, d) -> list:
    new_lst = lst[:]
    if d in new_lst:
        new_lst.remove(d)
    return new_lst

def without_key(dct: dict, k) -> dict:
    new_dct = dct.copy()
    if k in dct:
        new_dct.pop(k)
    return new_dct


def rep(d) -> str:
    return json.dumps(d, indent=2)


def compare_json(
        path: Path,
        json1: JSONPrimitive,
        json2: JSONPrimitive
):
    if json2 == "NOT IMPORTANT":
        return

    if json2 == "NOT FALSEY":
        if json1:
            return
        raise ValueError(f"{represent_path(path)}: {rep(json1)} is falsey")

    if json1 == "FALSEY":
        if not json1:
            return
        raise ValueError(f"{represent_path(path)}: {rep(json1)} is truthy")

    if isinstance(json2, list):
        if isinstance(json1, list):
            if len(json1) != len(without_element(json2, "UNORDERED")):
                raise ValueError(f"{represent_path(path)}: {rep(json1)} does not share the same length as {rep(json2)}")

            if "UNORDERED" in json2:
                for i, v in enumerate(json2):
                    if v == "UNORDERED": continue

                    compared = False
                    try:
                        compare_json(path + [i], json1[i], v)
                        compared = True
                    except Exception as e:
                        pass

                    if not compared:
                        raise ValueError(f"{represent_path(path)}: {rep(json1)} does not have {rep(v)}")

            else:
                for i, (j1, j2) in enumerate(zip(json1, json2)):
                    compare_json(path + [i], j1, j2)

            return
        else:
            raise ValueError(f"{represent_path(path)}: {rep(json1)} is not a list")

    if isinstance(json2, dict):
        if isinstance(json1, dict):
            if len(json1) != len(without_key(json2, "PARTIAL")):
                raise ValueError(f"{represent_path(path)}: {rep(json1)} does not share the same size as {rep(json2)}")

            if "PARTIAL" not in json2:
                if len(set(json1.keys()).symmetric_difference(set(json2.keys()))) != 0:
                    raise ValueError(f"{represent_path(path)}: {rep(json1)} contains too few or too much fields")

            for k, v in json2.items():
                if k == "PARTIAL": continue
                compare_json(path + [k], json1[k], v)

            return

        else:
            raise ValueError(f"{represent_path(path)}: {rep(json1)} is not an object")

    if json1 != json2:
        raise ValueError(f"{represent_path(path)}: {rep(json1)} is not {rep(json2)}")
