import os
import re
import time
import copy
import logging
import sys
from pathlib import Path

import pycparser as pyc

if __name__ != "__main__":
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import c_func_parser as cfp

class SafeLVGLGenerator():
    def __init__(self, 
        # Configs of SafeLVGLGenerator:
        lvgl_path : str, safe_lvgl_path : str, 
        
        template_header : str = 
            os.path.join(os.path.dirname(__file__), "header_template.h"),
        
        template_source : str = 
            os.path.join(os.path.dirname(__file__), "source_template.c"),
        
        template_func_decl : str = 
            os.path.join(os.path.dirname(__file__), "func_decl_template.h"),
        
        template_func_def  : str = 
            os.path.join(os.path.dirname(__file__), "func_def_template.c"),
        
        fake_libc_path : str = 
            os.path.join(os.path.dirname(__file__), "fake_libc_include"),

        # Configs of function generating:
        block_regex : list = [ r"^(_lv){1}" ], 
        safe_lvgl_prefix : str = "safe_"
        ):
        '''
        # Description:
            Initialize SafeLVGLGenerator.

        # Required parameter:
            lvgl_path: 
                Path of LVGL.

            safe_lvgl_path: 
                Output folder of safe LVGL.

            generate_func_def: 
                Function generating function, it's parameter is func_obj and 
                return values is function body in str.
                Example reference function `generate_safe_lvgl_def` in 
                SafeLVGLGenerator.py

            generate_func_decl: 
                Function generating function, same as above.

        # Optional parameters:
            compiler_path:
                Path of compiler(Only precompiling is used, so it doesn't matter
                which compiler you use).
            
            template_header: 
                The template header file used by the generated header file, you
                can include some header files or make other modifications here.

            template_source:
                Similar to template_header.

            fake_libc_path: 
                The fake headers path provided by pycparser (can also be 
                replaced with real headers).

            block_regex:
                The regex list of function names that should not be generated.

            safe_lvgl_prefix:
                The prefix of the generated function name.
        '''
        ############################## public  ##############################
        self.lvgl_version_major = 0
        self.lvgl_version_minor = 0
        self.lvgl_version_patch = 0

        # Logger.
        self.logger = logging.getLogger("safe_lvgl_generator")

        ############################## private ##############################
        # Configs.
        self._fake_libc_path = fake_libc_path
        self._lvgl_path = lvgl_path
        self._safe_lvgl_path = safe_lvgl_path

        # Init c_func_parser.
        self._parser = cfp.Parser("safe_lvgl_generator")

        # Block stragegies.
        self._blacklist_func_patterns = []
        for regex in block_regex:
            self._blacklist_func_patterns.append(re.compile(regex, re.X))

        # Safe LVGL prefix.
        self._safe_lvgl_prefix = safe_lvgl_prefix

        # Template files.
        self._template_header = template_header
        self._template_source = template_source

        # Load function template.
        self._template_func_decl = ""
        self._template_func_def  = ""
        with open(template_func_decl) as f:
            for line in f.readlines():
                line = line.replace('\r','').replace('\n','') + "\r\n"
                self._template_func_decl += line
        with open(template_func_def) as f:
            for line in f.readlines():
                line = line.replace('\r','').replace('\n','') + "\r\n"
                self._template_func_def += line

        # Function list.
        self._func_list = []


    def _get_realpath(self, relative_path : str) -> str:
        return os.path.realpath(os.path.join(self._lvgl_path, relative_path))

    
    def add_blacklist_func_pattern(self, func_pattern : re.Pattern):
        self._blacklist_func_patterns.append(func_pattern)

    
    def list_blacklist_func_patterns(self) -> list:
        return self._blacklist_func_patterns


    def get_lvgl_version(self) -> list:
        """
        # Get lvgl version.
        # Return: [major, minor, patch]
        """
        self.lvgl_version_major = 0
        self.lvgl_version_minor = 0
        self.lvgl_version_patch = 0
        # Prase lvgl version.
        lvgl_h_path = os.path.join(self._lvgl_path, "lvgl.h")

        # Regex and pattern.
        major_regex = r"^(\#define){1}[ ]+(LVGL_VERSION_MAJOR){1}[ ]+(?P<major_version>[0-9]+)"
        minor_regex = r"^(\#define){1}[ ]+(LVGL_VERSION_MINOR){1}[ ]+(?P<minor_version>[0-9]+)"
        patch_regex = r"^(\#define){1}[ ]+(LVGL_VERSION_PATCH){1}[ ]+(?P<patch_version>[0-9]+)"

        major_pattern = re.compile(major_regex, re.X)
        minor_pattern = re.compile(minor_regex, re.X)
        patch_pattern = re.compile(patch_regex, re.X)

        with open(lvgl_h_path, "r") as lvgl_h:
            line = lvgl_h.readline()
            while(line):
                line = line.replace('\r','').replace('\n','')
                # Match major version.
                if(not self.lvgl_version_major):
                    ret = major_pattern.match(line)
                    if(ret is not None):
                        self.lvgl_version_major = int(ret.group("major_version"))

                # Match minor version.
                if(not self.lvgl_version_minor):
                    ret = minor_pattern.match(line)
                    if(ret is not None):
                        self.lvgl_version_minor = int(ret.group("minor_version"))

                # Match patch version.
                if(not self.lvgl_version_patch):
                    ret = patch_pattern.match(line)
                    if(ret is not None):
                        self.lvgl_version_patch = int(ret.group("patch_version"))

                line = lvgl_h.readline()

        return [self.lvgl_version_major, self.lvgl_version_minor, \
            self.lvgl_version_patch]


    def _gen_lvgl_version(self) -> str:
        return "%s.%s.%s" % (self.lvgl_version_major, self.lvgl_version_minor, \
            self.lvgl_version_patch)


    def _gen_date(self) -> str:
        return time.strftime("%Y/%m/%d", time.localtime())
    

    def _gen_time(self) -> str:
        return time.strftime("%H:%M:%S", time.localtime())


    def _replace_variables(self, 
        original : str, contents : str, filename : str) -> str:
        original = original.replace(r"${contents_here}", contents)
        original = original.replace(r"${lvgl_version}", self._gen_lvgl_version())
        original = original.replace(r"${filename}", filename)
        original = original.replace(r"${date}", self._gen_date())
        original = original.replace(r"${time}", self._gen_time())
        return original


    def _output_safe_lvgl_api(self):
        # Output source file.
        source_file_content = ""
        for func in self._func_list:
            source_file_content += self._gen_func_def(func) + "\r\n\r\n"

        # Write source.
        template_source = open(self._template_source, "r")
        output_source = open(
            os.path.join(self._safe_lvgl_path, "safe_lvgl.c"), "wb+"
        )

        line = template_source.readline()
        while line:
            line = line.replace('\r','').replace('\n','') + "\r\n"
            line = self._replace_variables(line, source_file_content, 
                "safe_lvgl.c")
            
            output_source.write(bytes(line, encoding = 'utf-8'))
            line = template_source.readline()
        template_source.close()
        output_source.close()
        
        # Output header file.
        header_file_content = ""
        for func in self._func_list:
            header_file_content += self._gen_func_decl(func) + "\r\n\r\n"

        # Write header.
        template_header = open(self._template_header, "r")
        output_header = open(
            os.path.join(self._safe_lvgl_path, "safe_lvgl.h"), "wb+"
        )

        line = template_header.readline()
        while line:
            line = line.replace('\r','').replace('\n','') + "\r\n"
            line = self._replace_variables(line, header_file_content, 
                "safe_lvgl.h")
            
            output_header.write(bytes(line, encoding = 'utf-8'))
            line = template_header.readline()
        template_header.close()
        output_header.close()


    def parse(self, 
        cpp_path : str = "gcc", additional_cpp_args : list = []
        ) -> int:
        # Check lvgl version.
        if(not self.lvgl_version_major):
            self.get_lvgl_version()

        # List all folders containing header files.
        lvgl_include_path = []
        for parent, dirnames, filenames in os.walk(self._lvgl_path):
            parent_path = Path(parent)
            # Check if the folder contains header files.
            for filename in filenames:
                ext = os.path.splitext(filename)[1][1:]
                if ext =="h":
                    lvgl_include_path.append(str(parent_path))
                    break

        # Generate include_args.
        include_args = []
        for path in lvgl_include_path:
            include_args.append(r'-I{}'.format(path))
        cpp_args = [
            # Block std c include.
            "-nostdinc",

            # Use preprocess only.
            '-E',

            # Use LV_CONF_INCLUDE_SIMPLE.
            "-DLV_CONF_INCLUDE_SIMPLE",

            # Use PYCPARSER to disable gcc extensions.
            "-DPYCPARSER",

            # Include fake_libc.
            r'-I{}'.format(self._fake_libc_path)
            ] + include_args + additional_cpp_args

        # Parse interface header.
        self._func_list = self._parser.parse_file(
            path=os.path.join(self._lvgl_path, "lvgl.h"),
            use_cpp=True,
            cpp_path=cpp_path,
            cpp_args=cpp_args
        )

        function_count = len(self._func_list)

        # Generate safe api.
        self.logger.info("A total of {} functions were found in lvgl.h".\
            format(function_count))
        return function_count


    def get_lvgl_func_list(self) -> list:
        return self._func_list


    def gen_safe_lvgl(self):
        # Output source file.
        source_file_content = ""
        for func in self._func_list:
            source_file_content += self._gen_func_def(func) + "\r\n\r\n"
        self._output_safe_lvgl_api()


    def _gen_func_def(self, function : cfp.CFunc) -> str: 
        """
        # Description:
            Generate function definition of safe lvgl api using CFunc.

        # Parameters:
            function: C function in `CFunc`.

        # Returns:
            Function definition of safe lvgl api.
        """
        self.logger.debug("Generating function " + function.name + " defination:")
        func_def = self._template_func_def

        safe_func_decl = copy.deepcopy(function)
        safe_func_decl.name = self._safe_lvgl_prefix + function.name

        func_def = func_def.replace(r"${func_decl}", safe_func_decl.to_str(False))
        func_def = func_def.replace(r"${func_call}", function.gen_func_call())
        if(function.type != "void"):
            func_def = func_def.replace(r"${func_ret}", "return ret;")
        else:
            func_def = func_def.replace(r"${func_ret}", "")
        func_def = func_def.replace(r"${func_comms}", "") #TODO.

        self._replace_variables(func_def, "${contents_here}", "${filename}")
        self.logger.debug(func_def)
        return func_def


    def _gen_func_decl(self, function : pyc.c_ast.Decl) -> str: 
        # Generate function.
        self.logger.debug("Generating function " + function.name + " declaration:")
        func_decl = self._template_func_decl

        safe_func_decl = copy.deepcopy(function)
        safe_func_decl.name = self._safe_lvgl_prefix + function.name

        func_decl = func_decl.replace(r"${func_decl}", safe_func_decl.to_str(False))
        func_decl = func_decl.replace(r"${func_call}", function.gen_func_call())
        if(function.type != "void"):
            func_decl = func_decl.replace(r"${func_ret}", "return ret;")
        else:
            func_decl = func_decl.replace(r"${func_ret}", "")
        func_decl = func_decl.replace(r"${func_comms}", "") #TODO.

        self._replace_variables(func_decl, "${contents_here}", "${filename}")
        self.logger.debug(func_decl)
        return func_decl


def main():
    # Parse command parameters.
    import argparse
    parser = argparse.ArgumentParser()

    parser.add_argument("-l", "--lvgl", type = str, required = True, help = "Path of lvgl.")
    parser.add_argument("-o", "--output", type = str, required = True, help = "Output path of safe_lvgl.")

    parser.add_argument("--header", type = str, default = "./header_template.h", help = "Path of template header.")
    parser.add_argument("--source", type = str, default = "./source_template.c", help = "Path of template source.")
    parser.add_argument("--func_decl", type = str, default = "./func_decl_template.h", help = "Path of template function declaration file.")
    parser.add_argument("--func_def",  type = str, default = "./func_def_template.c",  help = "Path of template function defination file.")

    parser.add_argument("--prefix", type = str, default = "safe_", help = "Prefix of safe_lvgl api.")
    parser.add_argument("--block_regex", type = list, default = [], help = "Regex of functions to be blocked.")

    parser.add_argument("--cpp_path", type = str, default = "gcc", help = "Path of c compiler.")
    parser.add_argument("--cpp_args", type = list, default = [], help = "Additional arguments of c compiler.")

    args = parser.parse_args()

    # Generator.
    generator = SafeLVGLGenerator(
        lvgl_path=args.lvgl, safe_lvgl_path=args.output, 
        template_header=args.header, template_source=args.source,
        template_func_decl=args.func_decl, template_func_def=args.func_def,
        block_regex=args.block_regex,
        safe_lvgl_prefix=args.prefix
    )

    # Setup logger.
    generator.logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    generator.logger.addHandler(ch)

    # Generate safe_lvgl.
    generator.parse(args.cpp_path, args.cpp_args)
    generator.gen_safe_lvgl()


if __name__ == "__main__":
    main()
