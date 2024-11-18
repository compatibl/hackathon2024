try:
    from Levenshtein import editops
except {ImportError, ModuleNotFoundError}:
    editops = None

import re


def re2dict(m, start=None):
    offset = start["start"] if start else 0
    if re is None:
        return {}
    out = {
        "tag": m.group("tag"),
        "start": m.start() + offset,
        "end": m.end() + offset}
    out['idx'] = out['start']
    return out


def find_tags(original, tagged):
    tag_start = r"<(?P<tag>[a-z0-9]+?)>"
    tag_end = r"</(?P<tag>[a-z0-9]+?)>"
    tag_end_f = r"</(?P<tag>{tag})>"

    tag_starts = []
    tag_ends = []

    for start in re.finditer(tag_start, tagged, re.I):
        s = re2dict(start)
        tmp_end = tag_end_f.format(tag=start.group("tag"))
        end = re.search(tmp_end, tagged[start.start():], re.I)
        e = re2dict(end, s)
        if e:
            tag_starts.append(s)
            tag_ends.append(e)

    rebuilt = re.sub(tag_end, "", re.sub(tag_start, "", tagged))

    ops = {idx: op for op, _, idx in editops(original, rebuilt)}

    tag_offset = 0
    for idx in range(len(tagged)):
        in_tag = False
        for start, end in zip(tag_starts, tag_ends):
            if start["start"] <= idx < start["end"]:
                in_tag = True
            elif end["start"] <= idx < end["end"]:
                in_tag = True

        if in_tag:
            tag_offset -= 1
            for start, end in zip(tag_starts, tag_ends):
                if start["start"] > idx:
                    start['idx'] -= 1
                if end["start"] > idx:
                    end['idx'] -= 1

        elif idx + tag_offset in ops:
            op = ops.pop(idx + tag_offset)
            if op == "insert":
                for start, end in zip(tag_starts, tag_ends):
                    if start["start"] > idx:
                        start['idx'] -= 1
                    if end["start"] > idx:
                        end['idx'] -= 1

            elif op == "delete":
                for start, end in zip(tag_starts, tag_ends):
                    if start["start"] > idx:
                        start['idx'] += 1
                    if end["start"] > idx:
                        end['idx'] += 1
        idx += 1

    found_tags = {}
    for start, end in zip(tag_starts, tag_ends):
        found_tags.setdefault(start['tag'], [])
        tmp = original[start['idx']:end['idx']]
        found_tags[start['tag']].append(tmp)

    return found_tags


def py_editops(*args):
    if len(args) == 2:
        source_string, destination_string = args
        return _editops_from_strings(source_string, destination_string)
    elif len(args) == 3:
        edit_operations, source_length, destination_length = args
        return _editops_from_opcodes(edit_operations, source_length, destination_length)
    else:
        raise ValueError("Invalid number of arguments")

def _editops_from_strings(source, dest):
    m, n = len(source), len(dest)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(m + 1):
        for j in range(n + 1):
            if i == 0:
                dp[i][j] = j  # Insertions
            elif j == 0:
                dp[i][j] = i  # Deletions
            elif source[i - 1] == dest[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]  # No change
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j],    # Deletion
                    dp[i][j - 1],    # Insertion
                    dp[i - 1][j - 1] # Replacement
                )

    # Reconstruct the edit operations
    operations = []
    i, j = m, n
    while i > 0 or j > 0:
        if i > 0 and j > 0 and source[i - 1] == dest[j - 1]:
            i -= 1
            j -= 1
        elif j > 0 and (i == 0 or dp[i][j] == dp[i][j - 1] + 1):
            operations.append(('insert', i, j - 1))
            j -= 1
        elif i > 0 and (j == 0 or dp[i][j] == dp[i - 1][j] + 1):
            operations.append(('delete', i - 1, j))
            i -= 1
        else:
            operations.append(('replace', i - 1, j - 1))
            i -= 1
            j -= 1

    # Reverse to get the correct order
    operations.reverse()
    return operations

def _editops_from_opcodes(opcodes, source_length, destination_length):
    operations = []
    for op in opcodes:
        operation, spos, dpos = op
        operations.append((operation, spos, dpos))
    return operations

# If the library is not available then use the slower python one (AI generated, results not guaranteed)
if editops is None:
    editops = py_editops
