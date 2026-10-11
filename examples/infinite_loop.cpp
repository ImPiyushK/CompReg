// Controlled timeout demo (Scenario 3).
// Spins forever; CompReg must classify TIMEOUT after the configured timeout.
// The volatile counter prevents the empty loop from being optimized away, so
// the binary only terminates when the runner enforces its timeout.
#include <cstdio>

int main() {
    for (long long i = 0;; ++i) {
        if (i < 0) {  // never true until wrap-around (~years away)
            std::printf("unreachable\n");
        }
    }
    return 0;
}
