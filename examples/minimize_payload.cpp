// Minimization demo target (Scenario 6).
// Several dead helper functions surround a small, deliberately failing core:
// bad_mix() applies a wrong XOR constant. The printed checksum therefore
// never matches the trusted expected value, at every optimization level.
// Line-level delta debugging should be able to strip most helper lines while
// keeping the compile-and-fail predicate true.
//
// Trusted expected output (bad_mix replaced by good_mix, modeled in Python):
//   265
//   86
#include <cstdio>

[[maybe_unused]] static long long good_mix(long long x, long long salt) {
    long long v = (x + 977) * 31 + salt;
    v = v % 101;
    if (v < 0) {
        v += 101;
    }
    return v;
}

[[maybe_unused]] static long long dead_helper_a(long long seed) {
    long long acc = seed;
    for (int i = 0; i < 8; ++i) {
        acc = (acc * 7 + i) % 2011;
    }
    return acc;
}

[[maybe_unused]] static long long dead_helper_b(long long seed) {
    long long acc = 1;
    for (long long i = 0; i < seed; ++i) {  // bounded: seed <= 5
        acc = acc + i * 3;
    }
    return acc;
}

// INTENTIONAL BUG: applies ^= 101 instead of += 101 before masking; well
// defined, purely a logic error.
static long long bad_mix(long long x, long long salt) {
    long long v = (x + 977) * 31 + salt;
    v ^= 101;
    v = v % 101;
    if (v < 0) {
        v += 101;
    }
    return v;
}

int main() {
    long long sum = 0;
    for (long long i = 0; i < 5; ++i) {
        sum += good_mix(i, 2 * i);
    }
    long long bad = bad_mix(3, 6);
    std::printf("%lld\n", sum);
    std::printf("%lld\n", bad);
    return 0;
}
