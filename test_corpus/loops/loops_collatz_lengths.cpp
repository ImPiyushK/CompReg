// loops_collatz_lengths: 3n+1 chain lengths for n = 1..20 plus n = 27.
// For these inputs every intermediate value stays far below 2^63, so the
// loop is well defined and terminates.
#include <cstdio>

static long long collatz_steps(long long start) {
    long long value = start;
    long long steps = 0;
    while (value != 1) {
        if (value % 2 == 0) {
            value /= 2;
        } else {
            value = 3 * value + 1;
        }
        ++steps;
    }
    return steps;
}

int main() {
    for (int n = 1; n <= 20; ++n) {
        std::printf("%lld ", collatz_steps(n));
    }
    std::printf("\n");
    std::printf("%lld\n", collatz_steps(27));  // known chain length: 111
    return 0;
}
