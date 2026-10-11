// Controlled correctness regression demo (Scenario 2).
// This is a deliberately buggy copy of the corpus bubble sort: the
// comparison operator is inverted. The bug is a pure logic error - it
// introduces no undefined behavior - so a failure here is a program defect,
// not a compiler defect. Expected: CompReg classifies OUTPUT_MISMATCH.
#include <cstdio>

int main() {
    constexpr int n = 40;
    int data[n] = {
        40, 19, 3, 37, 25, 12, 8, 31, 2, 27,
        15, 39, 6, 22, 34, 10, 1, 28, 17, 36,
        5, 24, 20, 13, 38, 9, 30, 4, 26, 16,
        7, 33, 11, 23, 35, 14, 29, 18, 32, 21,
    };

    for (int pass = 0; pass < n - 1; ++pass) {
        bool swapped = false;
        for (int j = 0; j < n - 1 - pass; ++j) {
            // INTENTIONAL BUG: ascending comparison inverted.
            if (data[j] < data[j + 1]) {
                const int tmp = data[j];
                data[j] = data[j + 1];
                data[j + 1] = tmp;
                swapped = true;
            }
        }
        if (!swapped) {
            break;
        }
    }

    int sorted = 1;
    for (int i = 1; i < n; ++i) {
        if (data[i - 1] > data[i]) {
            sorted = 0;
        }
    }

    long long checksum = 0;
    for (int i = 0; i < n; ++i) {
        std::printf("%d ", data[i]);
        checksum += data[i];
    }
    std::printf("\n");
    std::printf("sorted=%d\n", sorted);
    std::printf("checksum=%lld\n", checksum);
    return 0;
}
