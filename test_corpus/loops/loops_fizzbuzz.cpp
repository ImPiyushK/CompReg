// loops_fizzbuzz: classic divisibility branching over a fixed range.
#include <cstdio>

int main() {
    for (int i = 1; i <= 45; ++i) {
        if (i % 15 == 0) {
            std::printf("FizzBuzz");
        } else if (i % 3 == 0) {
            std::printf("Fizz");
        } else if (i % 5 == 0) {
            std::printf("Buzz");
        } else {
            std::printf("%d", i);
        }
        std::printf("\n");
    }
    return 0;
}
