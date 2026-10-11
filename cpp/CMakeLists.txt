# CompReg C++ sources: the compreg_core kernel library, plus its tests.
add_library(compreg_core 
    src/bench_kernels.cpp
)
target_include_directories(compreg_core PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
target_compile_features(compreg_core PUBLIC cxx_std_17)
if(MSVC)
    target_compile_options(compreg_core PRIVATE /W4 /permissive-)
else()
    target_compile_options(compreg_core PRIVATE -Wall -Wextra)
endif()

if(COMPREG_BUILD_TESTS)
    add_subdirectory(tests)
endif()
