# Safe lvgl converter
A simple tool for making thread safe encapsulation api for lvgl.

## How it works
This tool uses [pycparser](https://github.com/eliben/pycparser) to parse the header file of lvgl and generate the corresponding thread safe api with mutexes (or other custom behaviors).

## Usage  
Usually, you just need to download the corresponding version of src in the Release and implement `safe_lvgl_init` , `lv_recursive_unlock` and `lv_recursive_lock` .  

## Custom output
When you need to customize the behavior in the safe_lvgl API, you need to change the template file and run this tool.  

### Custom template files
Reference [Variable table](https://github.com/h13-0/safe_lvgl_converter#Variable-table) and [Examples](https://github.com/h13-0/safe_lvgl_converter#Examples).  

### Requirements
* Python3
* pycparser >= 2.21
* C compilers such as gcc or msvc that support C99 **preprocessing**(Only the preprocessing function is required).

### Run with default configurations.
```bash
python SafeLVGL_Generator.py -l ${lvgl_path} -o ${output_path}
```
Helper:  
```bash
python SafeLVGL_Generator.py -h
```


## Variable table
| Variable           | Meaning                                | Example                                                                 |
| ------------------ | -------------------------------------- | ----------------------------------------------------------------------- |
| `${lvgl_version}`  | lvgl version in x.x.x                  | `8.3.3`                                                                 |
| `${contents_here}` | header or source content               | `safe_lvgl.h`                                                           |
| `${filename}`      | file name                              | `lvgl.h`                                                                |
| `${date}`          | date in yyyy-mm-dd                     | `2022-11-29`                                                            |
| `${time}`          | time in hh:mm:ss                       | `17:50:10`                                                              |
| `${func_decl}`     | function declaration without semicolon | `void safe_lv_init(void)`                                               |
| `${func_call}`     | function call with ret value           | `lv_obj_t * ret = lv_obj_create(parent);`</br>or</br>`lv_init();`       |
| `${func_ret}`      | return function value                  | `return ret`</br>or noting if void                                      |
| `${func_comms}`    | Comments for functions                 | Note that this variable does not guarantee cross version effectiveness. |

**note:**  
`${func_decl}` , `${func_call}` , `${func_ret}` , `${func_comms}` will only take effect in `func_decl_template.h` and `func_def_template.c`.

### Examples  
##### func_decl_template.h
template:
```C
${func_comms}
${func_decl};
```
Generate Results:  
```C
/**
 * Initialize LVGL library.
 * Should be called before any other LVGL related function.
 */
void safe_lv_init(void);
```

##### func_def_template.c
template:
```C
${func_decl}
{
    lv_recursive_unlock();
    ${func_call}
    lv_recursive_unlock();
    ${func_ret}
}
```
Generate Results:  
void case:  
```C
void safe_lv_init(void)
{
    lv_recursive_unlock();
    lv_init();
    lv_recursive_unlock();
}
```

Non void case:  
```C
lv_obj_t * safe_lv_obj_create(lv_obj_t * parent)
{
    lv_recursive_unlock();
    lv_obj_t * ret = lv_obj_create(parent);
    lv_recursive_unlock();
    return ret;
}
```

##### source_template.c  
template:  
```C
/**
 * @file: ${filename}
 * @note: This document is generated using [safe_lvgl_converter](https://github.com/h13-0/safe_lvgl_converter),
 *            based on lvgl version ${lvgl_version}.
 * @date: ${date}
 * @time: ${time}
 */
#include "safe_lvgl.h"


void safe_lvgl_init(void)
{
    // recursive mutex init.
}

static inline lv_recursive_unlock(void)
{
    // Unlock recursive mutex.
}

static inline lv_recursive_lock(void)
{
    // Lock recursive mutex.
}

${contents_here}

```
Generate Results:  
```C
/**
 * @file: safe_lvgl.c
 * @note: This document is generated using [safe_lvgl_converter](https://github.com/h13-0/safe_lvgl_converter),
 *            based on lvgl version 9.0.0.
 * @date: 2022/12/20
 * @time: 20:05:58
 */
#include "safe_lvgl.h"


void safe_lvgl_init(void)
{
    // recursive mutex init.
}

static inline lv_recursive_unlock(void)
{
    // Unlock recursive mutex.
}

static inline lv_recursive_lock(void)
{
    // Lock recursive mutex.
}

void safe_lv_tick_inc(uint32_t tick_period)
{
    lv_recursive_unlock();
    lv_tick_inc(tick_period);
    lv_recursive_lock();
}

...
```

##### header_template.h
template:  
```C
/**
 * @file: ${filename} 
 * @note: This document is generated using [safe_lvgl_converter](https://github.com/h13-0/safe_lvgl_converter),
 *            based on lvgl version $lvgl_version$.
 * @date: ${date}
 * @time: ${time}
 */

#ifndef __SAFE_LVGL_H__ 
#define __SAFE_LVGL_H__ 
#include "lvgl.h"

void safe_lvgl_init(void);

${contents_here}

#endif /* __SAFE_LVGL_H__ */

```
Generate Results:  
```C
/**
 * @file: safe_lvgl.h 
 * @note: This document is generated using [safe_lvgl_converter](https://github.com/h13-0/safe_lvgl_converter),
 *            based on lvgl version $lvgl_version$.
 * @date: 2022/12/20
 * @time: 20:05:58
 */

#ifndef __SAFE_LVGL_H__ 
#define __SAFE_LVGL_H__ 
#include "lvgl.h"

void safe_lvgl_init(void);

void safe_lv_tick_inc(uint32_t tick_period);
...
```

## Use as a plugin
```python
from safe_lvgl_converter import SafeLVGL_Generator

def main():
    # Parse.
    generator = SafeLVGL_Generator(
        lvgl_path = "...", safe_lvgl_path = "...",
        compiler_path = "gcc",
        template_header = "...", template_source = "...",
        template_func_decl = "...", template_func_def = "..."
    )

    # Generate safe_lvgl.
    generator.gen_safe_lvgl()

if __name__ == "__main__":
    main()

```
