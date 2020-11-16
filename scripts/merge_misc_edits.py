# Script to merge (Handler)TaskMiscEdit into (Handler)TaskEdit

import csv
import sys

from pathlib import Path

csv_path = Path(sys.argv[1])
csv_update_path = csv_path.with_name(
        csv_path.stem + '_merged' + csv_path.suffix)

with csv_path.open('rt') as f_csv, csv_update_path.open('wt') as f_csv_update:
    reader = csv.reader(f_csv)
    writer = csv.writer(f_csv_update)
    header = next(reader)
    t_misc_idx = header.index('TaskMiscEdit')
    ht_misc_idx = header.index('HandlerTaskMiscEdit')
    t_edit_idx = header.index('TaskEdit')
    ht_edit_idx = header.index('HandlerTaskEdit')

    assert ht_misc_idx < t_misc_idx
    assert ht_edit_idx < ht_misc_idx
    assert t_edit_idx < t_misc_idx

    header.remove('TaskMiscEdit')
    header.remove('HandlerTaskMiscEdit')
    writer.writerow(header)

    for line in reader:
        t_misc_str = line.pop(t_misc_idx)
        if t_misc_str == '':
            assert line[t_edit_idx] == ''
        else:
            t_misc_cnt = float(t_misc_str)
            line[t_edit_idx] = str(float(line[t_edit_idx]) + t_misc_cnt)

        ht_misc_str = line.pop(ht_misc_idx)
        if ht_misc_str == '':
            assert line[ht_edit_idx] == ''
        else:
            ht_misc_cnt = float(ht_misc_str)
            line[ht_edit_idx] = str(float(line[ht_edit_idx]) + ht_misc_cnt)

        writer.writerow(line)


# Verify
with csv_path.open('rt') as f_csv, csv_update_path.open('rt') as f_csv_update:
    reader = csv.reader(f_csv)
    reader_update = csv.reader(f_csv_update)

    t_misc_idx = ht_misc_idx = t_edit_idx = ht_edit_idx = 0
    for lidx, (l1, l2) in enumerate(zip(reader, reader_update)):  # noqa: C901
        assert len(l1) == len(l2) + 2
        i1 = i2 = 0
        while i1 < len(l1):
            e1 = l1[i1]
            e2 = l2[i2]
            if e1 in (
                    'TaskMiscEdit', 'HandlerTaskMiscEdit', 'TaskEdit',
                    'HandlerTaskEdit'):
                if e1 == 'TaskMiscEdit':
                    t_misc_idx = i1
                elif e1 == 'TaskEdit':
                    t_edit_idx = i1
                elif e1 == 'HandlerTaskMiscEdit':
                    ht_misc_idx = i1
                else:
                    assert e1 == 'HandlerTaskEdit'
                    ht_edit_idx = i1

                if 'MiscEdit' in e1:
                    assert e2 == l1[i1 + 1]
                    i1 += 1
                else:
                    assert e2 == e1
                    i1 += 1
                    i2 += 1
                continue
            if lidx == 0 or i1 not in (
                    t_misc_idx, ht_misc_idx, t_edit_idx, ht_edit_idx):
                assert e1 == e2, (e1, e2)
                i1 += 1
                i2 += 1
                continue

            if i1 in (ht_misc_idx, t_misc_idx):
                i1 += 1
                continue

            if e1 == '':
                assert e2 == '', e2
                i1 += 1
                i2 += 1
                continue

            if i1 == t_edit_idx:
                assert float(e2) == float(e1) + float(l1[t_misc_idx])
            else:
                assert i1 == ht_edit_idx
                assert float(e2) == float(e1) + float(l1[ht_misc_idx])
            i1 += 1
            i2 += 1
