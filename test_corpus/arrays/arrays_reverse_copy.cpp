// arrays_reverse_copy: reverse a fixed array and verify round-trip.
#include <cstdio>

int main() {
    constexpr int n = 8;
    const int original[n] = {3, 1, 4, 1, 5, 9, 2, 6};
    int reversed[n];

    for (int i = 0; i < n; ++i) {
        reversed[i] = original[n - 1 - i];
    }

    for (int i = 0; i < n; ++i) {
        std::printf("%d ", reversed[i]);
    }
    std::printf("\n");

    // Round-trip check: reversing twice restores the original.
    int restored[n];
    for (int i = 0; i < n; ++i) {
        restored[i] = reversed[n - 1 - i];
    }
    int matches = 1;
    for (int i = 0; i < n; ++i) {
        if (restored[i] != original[i]) {
            matches = 0;
        }
    }
    std::printf("%d\n", matches);
    return 0;
}
