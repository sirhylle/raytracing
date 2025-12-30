cmake_minimum_required(VERSION 3.15)
project(raytracing_cpp)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Python 3.8 REQUIRED COMPONENTS Interpreter Development.Module)
find_package(nanobind CONFIG REQUIRED)

nanobind_add_module(cpp_engine src/main.cpp)

# Enable OpenMP if available
find_package(OpenMP)
if(OpenMP_CXX_FOUND)
    target_link_libraries(cpp_engine PRIVATE OpenMP::OpenMP_CXX)
endif()

if(MSVC)
    target_compile_options(cpp_engine PRIVATE /fp:fast /O2)
else()
    target_compile_options(cpp_engine PRIVATE -Ofast -march=native)
endif()
