// boundary_guarded_division: division guards at the zero denominator edge.
#include <cstdio>

int main() {
    const int numerators[] = {100, 9, 9, -6, 77};
    const int denominators[] = {25, 4, 0, -2, 157};
    const int n = 5;

    for (int i = 0; i < n; ++i) {
        const int d = denominators[i];
        if (d == 0) {
            std::printf("skip\n");
        } else {
            std::printf("%d/%d=%d r%d\n", numerators[i], d,
                        numerators[i] / d, numerators[i] % d);
        }
    }
    return 0;
}
