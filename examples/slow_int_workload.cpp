// Deliberate performance-regression demo (Scenario 4/5).
// Semantically identical to test_corpus/benches/bench_int_workload.cpp and
// prints exactly the same checksums, but redundantly performs the whole
// deterministic workload a second time. The optimizer cannot collapse this:
// the mixed state chains are data-dependent multi-million-step computations.
// Result: identical output, several-fold slower wall-clock time.
//
// Trusted expected output (independent Python reference):
//   2023194183137462947
//   8241404432755619012
#include <cstdio>
#include <cstddef>

constexpr int OUTER_REPS = 40000;
constexpr int INNER_REPS = 700;

// Observable side effect that keeps the deliberately redundant workload
// alive; a volatile store cannot be optimized away or reordered out.
static volatile unsigned long long g_sink = 0;

static unsigned long long mix(unsigned long long x, unsigned long long salt) {
    x ^= salt;
    x *= 1103515245ULL;
    x += 12345ULL;
    x ^= x >> 33;
    x *= 0xFF51AFD7ED558CCDULL;
    x ^= x >> 33;
    return x;
}

static void run_once(unsigned long long &state, unsigned long long &accumulator) {
    for (int i = 0; i < OUTER_REPS; ++i) {
        for (int j = 0; j < INNER_REPS; ++j) {
            state = mix(state, static_cast<unsigned long long>(i * 31 + j));
            accumulator = (accumulator >> 1) | (accumulator << 63);
            accumulator ^= state & 0xFFFFULL;
            accumulator += (state >> 7) & 0xFFULL;
        }
    }
}

int main() {
    unsigned long long state = 2166136261ULL;
    unsigned long long accumulator = 0ULL;

    run_once(state, accumulator);

    // Deliberate degradation: recompute the identical workload; the volatile
    // store makes the result observable, so it cannot be eliminated.
    unsigned long long state2 = 2166136261ULL;
    unsigned long long accumulator2 = 0ULL;
    run_once(state2, accumulator2);
    g_sink = state2 ^ accumulator2;

    std::printf("%llu\n", accumulator);
    std::printf("%llu\n", state);
    return 0;
}
