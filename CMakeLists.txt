cmake_minimum_required(VERSION 3.15)
project(raytracing_cpp)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Python 3.8 REQUIRED COMPONENTS Interpreter Development.Module)

# On demande à l'exécutable Python trouvé ci-dessus où est installé nanobind
execute_process(
  COMMAND "${Python_EXECUTABLE}" -m nanobind --cmake_dir
  OUTPUT_VARIABLE NB_DIR
  OUTPUT_STRIP_TRAILING_WHITESPACE
)
# On ajoute ce chemin à la liste de recherche de CMake
list(APPEND CMAKE_PREFIX_PATH "${NB_DIR}")

find_package(nanobind CONFIG REQUIRED)

nanobind_add_module(cpp_engine src/main.cpp src/sobol.cpp)

# Enable OpenMP if available
find_package(OpenMP)
if(OpenMP_CXX_FOUND)
    target_link_libraries(cpp_engine PRIVATE OpenMP::OpenMP_CXX)
endif()

if(MSVC)
    # Windows : /arch:AVX2 active les instructions AVX2 et FMA (High Performance x86_64)
    target_compile_options(cpp_engine PRIVATE /O2 /fp:fast /arch:AVX2)
else()
    # Linux/Mac : -march=native optimise pour le CPU local (Intel ou Apple Silicon)
    # -Ofast active les optimisations agressives (fast-math)
    # target_compile_options(cpp_engine PRIVATE -Ofast -march=native)
    #target_compile_options(cpp_engine PRIVATE /O2 /fp:fast /arch:AVX2 /std:c++latest)
    target_compile_options(cpp_engine PRIVATE -Ofast -march=native -std=c++2b)
    
    # On ajoute -mfma uniquement sur x86_64 pour être explicite (souvent inclus dans native)
    # Sur ARM64 (Apple Silicon), FMA est standard et -mfma peut ne pas exister ou être un no-op
    if(NOT CMAKE_SYSTEM_PROCESSOR MATCHES "^(aarch64|arm64)")
        target_compile_options(cpp_engine PRIVATE -mfma)
    endif()
endif()