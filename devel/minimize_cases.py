"""
Filter and minimize raw inputs that exercise the second control-tuple
merge rule.
"""
from bsdiff4 import core
from bsdiff4.format import unpack_control_block

from devel.util import alphabetize, read_cases


def controls_for(src, dst):
    control, _, _ = core.diff(src, dst)
    return list(unpack_control_block(control))


def has_consecutive_ranges(controls):
    # Require two nonempty diff ranges so minimization cannot reduce the
    # first range to a no-op while still satisfying the predicate.
    for (px, py, pz), (x, y, z) in zip(controls, controls[1:]):
        if px > 0 and py == 0 and pz == 0 and x > 0:
            return True
    return False


def preserves_case(src, dst):
    controls = controls_for(src, dst)
    return has_consecutive_ranges(controls)


def ddmin(data, test):
    """Delete chunks until no partition complement satisfies test."""
    granularity = 2
    while len(data) >= 2:
        chunk_size = (len(data) + granularity - 1) // granularity
        for start in range(0, len(data), chunk_size):
            candidate = data[:start] + data[start + chunk_size:]
            if test(candidate):
                data = candidate
                granularity = max(2, granularity - 1)
                break
        else:
            if granularity >= len(data):
                break
            granularity = min(len(data), 2 * granularity)
    return data


def reduce_separately(src, dst):
    while True:
        old_sizes = len(src), len(dst)
        src = ddmin(src, lambda candidate: preserves_case(candidate, dst))
        dst = ddmin(dst, lambda candidate: preserves_case(src, candidate))
        if (len(src), len(dst)) == old_sizes:
            return src, dst


def reduce_together(src, dst):
    """Try deleting equal-sized chunks from both inputs at once."""
    size = min(len(src), len(dst)) // 2
    while size:
        for i in range(len(src) - size + 1):
            candidate_src = src[:i] + src[i + size:]
            for j in range(len(dst) - size + 1):
                candidate_dst = dst[:j] + dst[j + size:]
                if preserves_case(candidate_src, candidate_dst):
                    src, dst = candidate_src, candidate_dst
                    break
            else:
                continue
            break
        else:
            size //= 2
    return src, dst


def minimize(src, dst):
    while True:
        old_sizes = len(src), len(dst)
        src, dst = reduce_separately(src, dst)
        src, dst = reduce_together(src, dst)
        if (len(src), len(dst)) == old_sizes:
            return src, dst


def main():
    for src, dst in read_cases('branch2.raw'):
        blocks = core.diff(src, dst)
        assert core.patch(src, *blocks) == dst
        src, dst = minimize(src, dst)
        if not preserves_case(src, dst):
            continue
        if len(src) > 80 or len(dst) > 80:
            continue
        try:
            src, dst = alphabetize(src, dst)
        except ValueError:
            continue
        print("# " + 20 * '-')
        print("# %d %d (%d)" % (len(src), len(dst), len(set(src + dst))))
        print("# controls = %r" % controls_for(src, dst))
        print("src = %r" % src)
        print("dst = %r" % dst)


if __name__ == '__main__':
    main()
