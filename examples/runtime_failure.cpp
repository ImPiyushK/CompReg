// Controlled runtime-failure demo (Scenario 3).
// Prints a partial result and then exits deliberately with a nonzero code;
// CompReg must classify NONZERO_EXIT.
#include <cstdio>

int main() {
    std::printf("partial result: ");
    for (int i = 1; i <= 5; ++i) {
        std::printf("%d ", i * i);
    }
    std::printf("\n");
    return 3;  // intentional nonzero exit
}
