// branches_grade_classifier: multi-way branching including boundary cases.
// The 89/90 boundary is documented so regression in branching logic is caught.
#include <cstdio>

static char grade_of(int score) {
    if (score >= 90) {
        return 'A';
    } else if (score >= 80) {
        return 'B';
    } else if (score >= 70) {
        return 'C';
    } else if (score >= 60) {
        return 'D';
    }
    return 'F';
}

int main() {
    const int scores[] = {100, 95, 90, 89, 85, 80, 79, 72, 70, 69, 60, 59, 40, 0};
    for (int score : scores) {
        std::printf("%d=%c\n", score, grade_of(score));
    }
    return 0;
}
