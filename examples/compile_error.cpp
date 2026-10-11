// Controlled compilation-failure demo (Scenario 3).
// The syntax error below is intentional; CompReg must classify this test as
// COMPILE_ERROR and must never attempt to execute a binary.
#include <cstdio>

int main() {
    int x = 41
    std::printf("%d\n", x + 1);
    return 0;
}
