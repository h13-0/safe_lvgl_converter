import os
import re
import time
import copy
import logging
from pathlib import Path
import pycparser as pyc

class c_obj_decl:
    """
    # Description:
        This class is used to transfer the information in pyc.c_ast.Decl and provide the corresponding string.
        It is only applicable to type declaration and not suitable for detailed definition (such as bitsize in struct).
    # Methods:
        get_name:   Get the name of the object.
    """
    def __init__(self, name : str, quals : list, align : list, storage : list, real_type : str, array_layers : int, pointer_layers : int) -> None:
        """
        # Description:
            Constructor of c_obj_decl.
            
        # Parameters:
            name:           The name of the object.
            quals:          List of qualifiers (const, volatile).
            align:          Byte alignment.
                #Note: There are two cases:
                    _Alignas(2) int a;
                    _Alignas(char) int a;
            storage:        List of storage specifiers (extern, register, etc.).
            real_type:      The real type of the object.
            pointer_layers: The number of pointer layers.
            array_layers:   The number of array layers.
        """
        ############################## public  ##############################
        self.name = name
        self.quals = quals
        self.align = align
        self.storage = storage
        self.type = real_type
        self.array_layers = array_layers
        self.pointer_layers = pointer_layers


    def __str__(self) -> str:
        return self.to_str(semicolon = False, with_array = True)


    def type_to_str(self, space : bool = True) -> str:
        type_str = self.type
        if(self.pointer_layers):
            if(space):
                type_str += " "
            for i in range(self.pointer_layers):
                type_str += "*"
        return type_str


    def to_str(self, semicolon : bool = False, with_array : bool = False) -> str:
        decl = ""
        quals = self.quals_to_str()
        if(quals):
            decl += quals + " "
        
        align = self.align_to_str()
        if(align):
            decl += align + " "
        
        storage = self.storage_to_str()
        if(storage):
            decl += storage + " "
        
        if(self.type_to_str() != "void"):
            decl += self.type_to_str() + " " + self.name_to_str(with_array = with_array)
        else:
            decl += self.type_to_str()

        if(semicolon):
            decl += ";"
        return decl


    def quals_to_str(self) -> str:
        return " ".join(self.quals)


    def align_to_str(self) -> str:
        return " ".join(self.align)


    def storage_to_str(self) -> str:
        return " ".join(self.storage)

    def name_to_str(self, with_array : bool = False):
        if(with_array):
            name = self.name
            for i in range(self.array_layers):
                name += "[]"
            return name
        else:
            return self.name


class c_func_obj_decl(c_obj_decl):
    def __init__(self, name : str, quals : list, storge : list, funcspec : list, return_type : str, array_layers : int, pointer_layers : int, params : list) -> None:
        """
        # Description:
            Constructor of c_func_obj_decl.
            
        # Parameters:
            name:           The name of the function.
            quals:          List of qualifiers (const, volatile).
            storage:        List of storage specifiers (extern, register, etc.).
            funcspec:       Function specifiers, (i.e. inline in C99 and _Noreturn_ in C11).
            return_type:    The real return type of the function.
            pointer_layers: The number of pointer layers.
            params:         The arguments of the function.
        """
        super().__init__(name = name, quals = quals, align = "", storage = storge, real_type = return_type, array_layers = array_layers, pointer_layers = pointer_layers)
        ############################## public  ##############################
        self.funcspec = funcspec
        self.return_type = return_type
        self.params = params


    def __str__(self) -> str:
        return self.to_str(True)


    def funcspec_to_str(self) -> str:
        return " ".join(self.funcspec)


    def params_to_str(self) -> str:
        params = []
        for param in self.params:
            params.append(param.to_str(semicolon = False, with_array = True))
        return ", ".join(params)


    def to_str(self, semicolon : bool = False) -> str:
        """
        # Description:
            Generate the declaration of the function.
        # Parameters:
            semicolon:  Whether to add semicolon at the end of the declaration.
        """
        decl = ""
        quals = self.quals_to_str()
        if(quals):
            decl = quals + " "
        
        storage = self.storage_to_str()
        if(storage):
            decl += storage + " "
        funcspec = self.funcspec_to_str()
        if(funcspec):
            decl += funcspec + " "
        decl += self.type_to_str() + " " + self.name_to_str(True) + "(" + self.params_to_str() + ")"
        if(semicolon):
            decl += ";"
        return decl


    def get_return_type(self) -> str:
        return self.return_type

    
    def gen_func_call(self) -> str:
        func_call = ""
        func_param = ""
        param_nums = len(self.params)
        for i in range(param_nums):
            if(i < param_nums - 1):
                if(self.params[i].type_to_str() != "void"):
                    func_param += self.params[i].name + ", "
            else:
                if(self.params[i].type_to_str() != "void"):
                    func_param += self.params[i].name        
        
        if(self.type_to_str() != "void"):
            func_call += self.type_to_str() + " ret = " + self.name + "(" + func_param + ");"
        else:
            func_call += self.name + "(" + func_param + ");"

        return func_call


class SafeLVGL_Generator:
    def __init__(self, lvgl_path : str, safe_lvgl_path : str, 
        compiler_path : str = "gcc", 
        template_header : str = os.path.join(os.path.dirname(__file__), "header_template.h"),
        template_source : str = os.path.join(os.path.dirname(__file__), "source_template.c"),
        template_func_decl : str = os.path.join(os.path.dirname(__file__), "func_decl_template.h"),
        template_func_def  : str = os.path.join(os.path.dirname(__file__), "func_def_template.c"),
        fake_libc_path : str = os.path.join(os.path.dirname(__file__), "fake_libc_include")
        ):
        '''
        # Required parameter:
            lvgl_path:          Path of LVGL.
            safe_lvgl_path:     Output folder of safe LVGL.
            generate_func_def:  Function generating function, it's parameter is func_obj and return values is function body in str.
                                Example reference function `generate_safe_lvgl_def` in SafeLVGL_Generator.py
            generate_func_decl: Function generating function, same as above.

        # Optional parameters:
            compiler_path:      Path of compiler(Only precompiling is used, so it doesn't matter which compiler you use).
            template_header:    The template header file used by the generated header file, you can include some header files or make other modifications here.
            template_source:    Ditto.
            fake_libc_path:     The fake headers path provided by pycparser (can also be replaced with real headers).
        '''
        ############################## public  ##############################
        self.lvgl_version_major = 0
        self.lvgl_version_minor = 0
        self.lvgl_version_patch = 0
        # Logger.
        self.logger = logging.getLogger("safe_lvgl_generator")

        ############################## private ##############################
        self.__fake_libc_path__ = fake_libc_path
        self.__lvgl_path__ = lvgl_path
        self.__compiler_path__ = compiler_path
        self.__safe_lvgl_path__ = safe_lvgl_path

        # block stragegies.
        self.__blacklist_func_patterns__ = []

        # Load default block strategy.
        self.load_default_block_strategy()

        # Template files.
        self.__template_header__ = template_header
        self.__template_source__ = template_source

        # Function template.
        self.__template_func_decl__ = ""
        self.__template_func_def__  = ""
        with open(template_func_decl) as f:
            for line in f.readlines():
                line = line.replace('\r','').replace('\n','') + "\r\n"
                self.__template_func_decl__ += line
        with open(template_func_def) as f:
            for line in f.readlines():
                line = line.replace('\r','').replace('\n','') + "\r\n"
                self.__template_func_def__ += line

        # Function list.
        self.__func_list__ = []


    def __get__realpath__(self, relative_path : str) -> str:
        return os.path.realpath(os.path.join(self.__lvgl_path__, relative_path))


    def load_default_block_strategy(self):
        """
        # The safe api generation strategy is based on filtering blacklist paths/files/functions on the allowed paths/files.
        # The masking strategy for functions is regular expressions.
        """

        self.__blacklist_func_patterns__ = [
            re.compile(r"^(_lv){1}", re.X)
        ]

    
    def add_blacklist_func_pattern(self, func_pattern : re.Pattern):
        self.__blacklist_func_patterns__.append(func_pattern)

    
    def list_blacklist_func_patterns(self) -> list:
        return self.__blacklist_func_patterns__


    def get_lvgl_version(self) -> list:
        """
        # Get lvgl version.
        # Return: [major, minor, patch]
        """
        self.lvgl_version_major = 0
        self.lvgl_version_minor = 0
        self.lvgl_version_patch = 0
        # Prase lvgl version.
        lvgl_h_path = os.path.join(self.__lvgl_path__, "lvgl.h")

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

        return [self.lvgl_version_major, self.lvgl_version_minor, self.lvgl_version_patch]


    def __add_lvgl_func__(self, func_node : pyc.c_ast.Decl) -> bool:
        '''
        # Description:
            Add and summarize the functions provided by lvgl.
            When the name of this function meet the requirements and there are no duplicates, it will be added to the list and return True.

        # Parameters:
            func_node:  AST node of function in `pycparser.c_ast.Decl`.
        '''
        # Get function name.    
        func_name = func_node.name

        # Check if function is in blacklist.
        for func_pattern in self.__blacklist_func_patterns__:
            if(func_pattern.match(func_name)):
                self.logger.info("Function {} is in blacklist.".format(func_name))
                return False

        # Check if function has been added to the list.
        for func in self.__func_list__:
            if func_name == func.name:
                return False

        # Add function to list.
        func = None
        try:
            func = self.c_decl_to_c_obj(func_node)
        except NotImplementedError as e:
            self.logger.warning("Parse function error: " + func_name + " error: "+ str(e))

        if(func is not None):
            self.__func_list__.append(func)
        else:
            return False

        return True


    def __parse_header__(self, header_path : str, cpp_args : list) -> int:
        """
        # Description:
            Parse header file and generate safe api.
        """

        # Parse header file.
        self.logger.info("Parsing {} ...".format(header_path))
        ast = pyc.parse_file(header_path, use_cpp = True, cpp_path = self.__compiler_path__, cpp_args = cpp_args)
        
        for node in ast.ext:
            if isinstance(node, pyc.c_ast.FuncDef):
                # Is FuncDef.
                self.__add_lvgl_func__(node.decl)

            elif(isinstance(node, pyc.c_ast.Decl) and isinstance(node.type, pyc.c_ast.FuncDecl)):
                # Is FuncDecl.
                self.__add_lvgl_func__(node)

        return len(self.__func_list__)


    def __gen_lvgl_version_(self) -> str:
        return "%s.%s.%s" % (self.lvgl_version_major, self.lvgl_version_minor, self.lvgl_version_patch)


    def __gen_date__(self) -> str:
        return time.strftime("%Y/%m/%d", time.localtime())
    

    def __gen_time__(self) -> str:
        return time.strftime("%H:%M:%S", time.localtime())


    def __replace_variables__(self, original : str, contents : str, filename : str) -> str:
        original = original.replace(r"${contents_here}", contents)
        original = original.replace(r"${lvgl_version}", self.__gen_lvgl_version_())
        original = original.replace(r"${filename}", filename)
        original = original.replace(r"${date}", self.__gen_date__())
        original = original.replace(r"${time}", self.__gen_time__())
        return original


    def __output_safe_lvgl_api__(self):
        # Output source file.
        source_file_content = ""
        for func in self.__func_list__:
            source_file_content += self.__gen_func_def__(func) + "\r\n\r\n"

        # Write source.
        template_source = open(self.__template_source__, "r")
        output_source = open(os.path.join(self.__safe_lvgl_path__, "safe_lvgl.c"), "wb+")
        line = template_source.readline()
        while line:
            line = line.replace('\r','').replace('\n','') + "\r\n"
            line = self.__replace_variables__(line, source_file_content, "safe_lvgl.c")
            output_source.write(bytes(line, encoding = 'utf-8'))
            line = template_source.readline()
        template_source.close()
        output_source.close()
        
        # Output header file.
        header_file_content = ""
        for func in self.__func_list__:
            header_file_content += self.__gen_func_decl__(func) + "\r\n\r\n"

        # Write header.
        template_header = open(self.__template_header__, "r")
        output_header = open(os.path.join(self.__safe_lvgl_path__, "safe_lvgl.h"), "wb+")
        line = template_header.readline()
        while line:
            line = line.replace('\r','').replace('\n','') + "\r\n"
            line = self.__replace_variables__(line, header_file_content, "safe_lvgl.h")
            output_header.write(bytes(line, encoding = 'utf-8'))
            line = template_header.readline()
        template_header.close()
        output_header.close()


    def parse(self, additional_cpp_args : list = []) -> int:
        # Check lvgl version.
        if(not self.lvgl_version_major):
            self.get_lvgl_version()

        # List all folders containing header files.
        lvgl_include_path = []
        for parent, dirnames, filenames in os.walk(self.__lvgl_path__):
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
            r'-I{}'.format(self.__fake_libc_path__)
            ] + include_args + additional_cpp_args

        # Parse interface header.
        function_count = self.__parse_header__(os.path.join(self.__lvgl_path__, "lvgl.h"), cpp_args)

        # Generate safe api.
        self.logger.info("A total of {} functions were found in lvgl.h".format(function_count))
        return function_count


    def get_lvgl_func_list(self) -> list:
        return self.__func_list__


    def gen_safe_lvgl(self):
        # Output source file.
        source_file_content = ""
        for func in self.__func_list__:
            source_file_content += self.__gen_func_def__(func) + "\r\n\r\n"
        self.__output_safe_lvgl_api__()

    class EllipsisParamException(NotImplementedError):
        def __init__(self, *args):
            self.args = args


    def __get_nesting_type__(self, node) -> list:
        """
        # Description:
            Get the real type nested by array and pointer.
        
        # Return:
            list in [ c_obj_type, c_obj_array_layers, c_obj_pointer_layers ]
        """
        c_obj_array_layers = 0
        c_obj_pointer_layers = 0
        
        # Get nesting levels.
        child_node = node
        while(isinstance(child_node, pyc.c_ast.ArrayDecl)):
            c_obj_array_layers += 1
            child_node = child_node.type
        while(isinstance(child_node, pyc.c_ast.PtrDecl)):
            c_obj_pointer_layers += 1
            child_node = child_node.type

        if(isinstance(child_node, pyc.c_ast.Typename)):
            child_node = child_node.type

        if(isinstance(child_node, pyc.c_ast.TypeDecl)):
            parent_type = child_node.type
            if(isinstance(parent_type, pyc.c_ast.Struct)):
                return [ "struct " + parent_type.name, c_obj_array_layers, c_obj_pointer_layers ]
            elif(isinstance(parent_type, pyc.c_ast.IdentifierType)):
                return [ parent_type.names[0], c_obj_array_layers, c_obj_pointer_layers ]
            else:
                # TODO: pyc.c_ast.Union
                raise Exception("Unknown type in TypeDecl: " + str(parent_type))

        raise Exception("Unknown type: " + str(node))


    def c_decl_to_c_obj(self, node) -> c_obj_decl:
        """
        # Description:
            Convert function, c object, function param to c_obj.
            Only function declaration, c object declaration and function param are supported.

        # Return:
            c function in c_func_decl or c object in c_obj_decl.
        """
        # pyc.c_ast.Decl has the following properties:
        ##  name:       the variable being declared
        ##  quals:      list of qualifiers (const, volatile, restrict)
        ##  align:      byte alignment.
        ##  storage:    list of storage specifiers (extern, register, etc.)
        ##  funcspec:   list function specifiers (i.e. inline in C99 and _Noreturn_ in C11)
        ##  type:       declaration type, the type in the function node is pyc.c_ast.FuncDecl.
        ##  init:       initialization value, or None
        ##  bitsize:    bit field size, or None
        c_obj_name = ""
        c_obj_quals = []
        c_obj_align = []
        c_obj_storage = []
        c_obj_funcspec = []
        c_obj_type = ""
        c_obj_pointer_layers = 0
        c_obj_array_layers = 0
        c_obj_params = []

        is_function = False

        # process Decl
        if(isinstance(node, pyc.c_ast.Decl)):
            # Get name.
            c_obj_name = node.name
            
            # Get qualifiers.
            c_obj_quals = node.quals

            # TODO: align
            if(len(node.align) > 0):
                raise Exception("Align is not supported temporarily.")
            
            # Get storage specifiers.
            c_obj_storage = node.storage

            # Get funcspecs.
            c_obj_funcspec = node.funcspec

            # Check type.
            if(isinstance(node.type, pyc.c_ast.ArrayDecl)):
                c_obj_type, c_obj_array_layers, c_obj_pointer_layers = self.__get_nesting_type__(node.type)

            elif(isinstance(node.type, pyc.c_ast.Decl)):
                # I don't think Decl should appear, but it needs to be verified.
                raise Exception("The Decl should no longer appear in the Decl.")

            elif(isinstance(node.type, pyc.c_ast.Enum)):
                # Enum, such as:
                # Declaration:
                #   enum enum_type { a, b, c };
                # Object:
                #   enum_type obj; // Type of obj is enum.
                # Type name:
                #   name    -> enum_type
                c_obj_type = "enum " + node.type.name

            elif(isinstance(node.type, pyc.c_ast.FuncDecl)):
                is_function = True
                # Get params.
                for param in node.type.args:
                    c_obj_params.append(self.c_decl_to_c_obj(param))
                # Get type.
                c_obj_type, c_obj_array_layers, c_obj_pointer_layers = self.__get_nesting_type__(node.type.type)

            elif(isinstance(node.type, pyc.c_ast.PtrDecl)):
                # Pointer declaration, such as:
                #   int *a;
                c_obj_type, c_obj_array_layers, c_obj_pointer_layers = self.__get_nesting_type__(node.type)

            elif(isinstance(node.type, pyc.c_ast.TypeDecl)):
                # TypeDecl, such as:
                #   int a;
                c_obj_type, c_obj_array_layers, c_obj_pointer_layers = self.__get_nesting_type__(node.type)

            elif(isinstance(node.type, pyc.c_ast.Typename)):
                # Typename, such as:
                #   void func(int);
                # Then `int`` in the params is Typename.
                c_obj_type, c_obj_array_layers, c_obj_pointer_layers = self.__get_nesting_type__(node.type.type)
                
                raise Exception("TODO.")

            else:
                # such as: ArrayRef, Assignment, Alignas ...
                raise Exception("Types that should not appear: " + str(node.type))

        # Process TypeDecl.
        elif(isinstance(node, pyc.c_ast.TypeDecl)):
            c_obj_type, c_obj_array_layers, c_obj_pointer_layers = self.__get_nesting_type__(node)

        # Process Typename.
        elif(isinstance(node, pyc.c_ast.Typename)):
            # Get name.
            c_obj_name = node.name
            c_obj_quals = node.quals
            # TODO: align
            if(isinstance(node.type, pyc.c_ast.TypeDecl)):
                c_obj_type, c_obj_array_layers, c_obj_pointer_layers = self.__get_nesting_type__(node)
            else:
                raise Exception("TODO, node: " + str(node))

        elif(isinstance(node, pyc.c_ast.EllipsisParam)):
            raise self.EllipsisParamException("EllipsisParam is not supported temporarily.")

        else:
            raise TypeError("Should not appear other types, node: " + str(node))

        if(is_function):
            return c_func_obj_decl(c_obj_name, c_obj_quals, c_obj_storage, c_obj_funcspec, c_obj_type, c_obj_array_layers, c_obj_pointer_layers, c_obj_params)
        else:
            return c_obj_decl(c_obj_name, c_obj_quals, c_obj_align, c_obj_storage, c_obj_type, c_obj_array_layers, c_obj_pointer_layers)


    def __gen_func_def__(self, function : c_func_obj_decl) -> str: 
        """
        # Description:
            Generate function definition of safe lvgl api using c_func_obj_decl.

        # Parameters:
            function: C function in `c_func_obj_decl`.

        # Returns:
            Function definition of safe lvgl api.
        """
        self.logger.debug("Generating function " + function.name + " defination:")
        func_def = self.__template_func_def__

        safe_func_decl = copy.deepcopy(function)
        safe_func_decl.name = "safe_" + function.name

        func_def = func_def.replace(r"${func_decl}", safe_func_decl.to_str(False))
        func_def = func_def.replace(r"${func_call}", function.gen_func_call())
        if(function.type != "void"):
            func_def = func_def.replace(r"${func_ret}", "return ret;")
        else:
            func_def = func_def.replace(r"${func_ret}", "")
        func_def = func_def.replace(r"${func_comms}", "") #TODO.

        self.__replace_variables__(func_def, "${contents_here}", "${filename}")
        self.logger.debug(func_def)
        return func_def


    def __gen_func_decl__(self, function : pyc.c_ast.Decl) -> str: 
        # Generate function.
        self.logger.debug("Generating function " + function.name + " declaration:")
        func_decl = self.__template_func_decl__

        safe_func_decl = copy.deepcopy(function)
        safe_func_decl.name = "safe_" + function.name

        func_decl = func_decl.replace(r"${func_decl}", safe_func_decl.to_str(False))
        func_decl = func_decl.replace(r"${func_call}", function.gen_func_call())
        if(function.type != "void"):
            func_decl = func_decl.replace(r"${func_ret}", "return ret;")
        else:
            func_decl = func_decl.replace(r"${func_ret}", "")
        func_decl = func_decl.replace(r"${func_comms}", "") #TODO.

        self.__replace_variables__(func_decl, "${contents_here}", "${filename}")
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

    args = parser.parse_args()

    # Parse
    generator = SafeLVGL_Generator(
        lvgl_path = args.lvgl, safe_lvgl_path = args.output, 
        compiler_path = "gcc", # Or use "cl" to select msvc, but I haven't tested.
        template_header = args.header, template_source = args.source,
        template_func_decl = args.func_decl, template_func_def = args.func_def
    )

    # Setup logger.
    generator.logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    generator.logger.addHandler(ch)

    # Generate safe_lvgl.
    generator.parse()
    generator.gen_safe_lvgl()


if __name__ == "__main__":
    main()
