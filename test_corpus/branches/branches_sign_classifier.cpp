// branches_sign_classifier: simple relational branching over distinct sign axes.
#include <cstdio>

static const char *sign_of(int value) {
    if (value > 0) {
        return "positive";
    } else if (value < 0) {
        return "negative";
    }
    return "zero";
}

int main() {
    const int values[] = {7, 1, 0, -1, -42, 2147483646, -2147483647};
    for (int value : values) {
        std::printf("%d:%s\n", value, sign_of(value));
    }
    return 0;
}
