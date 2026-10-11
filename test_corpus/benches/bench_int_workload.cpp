// bench_int_workload: deterministic integer pipeline, checksum printed once.
// The LCG xorshift mixing chain is bounded unsigned arithmetic.
// Workload target: tens of ms at -O2, several hundred ms at -O0.
#include <cstdio>

constexpr int OUTER = 40000;
constexpr int INNER = 700;

static unsigned long long mix(unsigned long long x, unsigned long long salt) {
    x ^= salt;
    x *= 1103515245ULL;
    x += 12345ULL;
    x ^= x >> 33;
    x *= 0xFF51AFD7ED558CCDULL;
    x ^= x >> 33;
    return x;
}

int main() {
    unsigned long long state = 2166136261ULL;
    unsigned long long accumulator = 0ULL;

    for (int i = 0; i < OUTER; ++i) {
        for (int j = 0; j < INNER; ++j) {
            state = mix(state, static_cast<unsigned long long>(i * 31 + j));
            accumulator = (accumulator >> 1) | (accumulator << 63);
            accumulator ^= state & 0xFFFFULL;
            accumulator += (state >> 7) & 0xFFULL;
        }
    }

    std::printf("%llu\n", accumulator);
    std::printf("%llu\n", state);
    return 0;
}
