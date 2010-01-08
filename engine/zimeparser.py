#!/usr/bin/env python
# -*- coding: utf-8 -*-

from ibus import keysyms
from ibus import modifier

from zimecore import *

class RomanParser(Parser):
    def __init__(self, schema):
        Parser.__init__(self, schema)
        self.__auto_prompt = schema.get_config_value(u'AutoPrompt') in (u'yes', u'true')
        self.__alphabet = schema.get_config_char_sequence(u'Alphabet') or \
                          u'abcdefghijklmnopqrstuvwxyz'
        self.__initial = self.__alphabet.split(None, 1)[0]
        self.__delimiter = schema.get_config_char_sequence(u'Delimiter') or u' '
        self.__quote = schema.get_config_char_sequence('Quote') or u'`'
        acc = (schema.get_config_char_sequence('Acceptable') or \
               u'''ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz
                   0123456789!@#$%^&*()`~-_=+[{]}\\|;:'",<.>/?''').split(None, 1)
        self.__acceptable = lambda x: x == u' ' or any([x in s for s in acc])
        self.__initial_acceptable = lambda x: x in self.__quote or x in acc[0]
        get_rules = lambda f, key: [f(r.split()) for r in schema.get_config_list(key)]
        compile_repl_pattern = lambda x: (re.compile(x[0]), x[1])
        self.__xform_rules = get_rules(compile_repl_pattern, u'TransformRule')
        self.clear()
    def clear(self):
        self.__input = []
        self.__prompt = u''
    def __is_empty(self):
        return not bool(self.__input)
    def __get_input(self):
        if self.__xform_rules:
            # apply transform rules
            xform = lambda s, r: r[0].sub(r[1], s)
            s = reduce(xform, self.__xform_rules, u''.join(self.__input))
            return list(s)
        else:
            return self.__input[:]
    def process_input(self, event, ctx):
        if event.mask & modifier.RELEASE_MASK:
            return False
        ch = event.get_char()
        # raw string mode
        if self.__prompt:
            p = self.__prompt
            if event.keycode == keysyms.Return:
                if len(p) > 1 and p[0] in self.__quote:
                    return Commit(p[1:]) 
                else:
                    return Commit(p)
            if event.keycode == keysyms.Escape:
                self.clear()
                return Prompt()
            if event.keycode == keysyms.BackSpace:
                self.__prompt = p[:-1]
                return Prompt(self.__prompt)
            if ch in self.__quote and p[0] in self.__quote:
                return Commit(p + ch)
            if self.__acceptable(ch):
                self.__prompt += ch
                return Prompt(self.__prompt)
            return True
        # disable input in conversion mode
        if not self.__auto_prompt and ctx.being_converted():
            return False
        # normal mode
        if event.keycode == keysyms.Escape:
            self.clear()
            if self.__xform_rules and ctx.has_error():
                ctx.edit([])
                return True
            return False
        if event.keycode == keysyms.BackSpace:
            if self.__is_empty():
                return False
            self.__input.pop()
            ctx.input = self.__get_input()
            return []
        if event.keycode == keysyms.space:
            return False
        if self.__is_empty() and ch in self.__initial or \
           not self.__is_empty() and (ch in self.__alphabet or ch in self.__delimiter):
            self.__input.append(ch)
            ctx.input = self.__get_input()
            return []
        # start raw string mode
        if self.__is_empty() and self.__initial_acceptable(ch):
            self.__prompt = ch
            return Prompt(self.__prompt)
        # unused
        return False

class GroupingParser(Parser):
    def __init__(self, schema):
        Parser.__init__(self, schema)
        self.__auto_prompt = schema.get_config_value(u'AutoPrompt') in (u'yes', u'true')
        self.__auto_predict = schema.get_config_value(u'Predict') in (None, u'yes', u'true')
        self.__prompt_pattern = schema.get_config_char_sequence(u'PromptPattern') or u'%s\u203a'
        self.__delimiter = schema.get_config_char_sequence(u'Delimiter') or u' '
        self.__key_groups = schema.get_config_value(u'KeyGroups').split()
        self.__code_groups = schema.get_config_value(u'CodeGroups').split()
        self.__group_count = len(self.__key_groups)
        self.clear()
    def clear(self):
        self.__slots = [u''] * self.__group_count
        self.__cursor = 0
    def __is_empty(self):
        return not any(self.__slots)
    def __get_prompt(self, first):
        text = self.__prompt_pattern % u''.join(self.__slots)
        padding = None if first or self.__auto_predict else self.__delimiter[0]
        return Prompt(text, padding=padding)
    def process_input(self, event, ctx):
        if event.mask & modifier.RELEASE_MASK:
            return False
        if not self.__auto_prompt and ctx.being_converted():
            return False
        if event.keycode == keysyms.Escape:
            self.clear()
            return False
        if event.keycode == keysyms.BackSpace:
            if self.__is_empty():
                return False
            # delete last one symbol from current keyword
            j = self.__group_count - 1
            while j > 0 and not self.__slots[j]:
                j -= 1
            self.__slots[j] = u''
            while j > 0 and not self.__slots[j]:
                j -= 1
            self.__cursor = j
            if not self.__is_empty():
                # update prompt
                return self.__get_prompt(ctx.is_empty())
            else:
                # keyword disposed
                self.clear()
                return Prompt()
        if event.keycode == keysyms.space:
            if self.__is_empty():
                return False
            result = u''.join(self.__slots)
            self.clear()
            return [result] if ctx.is_empty() else [self.__delimiter[0], result]
        # handle grouping input
        ch = event.get_char()
        k = self.__cursor
        while ch not in self.__key_groups[k]:
            k += 1
            if k >= self.__group_count:
                k = 0
            if k == self.__cursor:
                if self.__is_empty():
                    return False
                else:
                    return True
        # update current keyword
        idx = self.__key_groups[k].index(ch)
        self.__slots[k] = self.__code_groups[k][idx]
        k += 1
        if k >= self.__group_count:
            keyword = u''.join(self.__slots)
            self.clear()
            return [keyword] if ctx.is_empty() else [self.__delimiter[0], keyword]
        else:
            self.__cursor = k
            return self.__get_prompt(ctx.is_empty())

class ComboParser(Parser):
    def __init__(self, schema):
        Parser.__init__(self, schema)
        self.__auto_predict = schema.get_config_value(u'Predict') in (None, u'yes', u'true')
        self.__prompt_pattern = schema.get_config_char_sequence(u'PromptPattern') or u'%s\u203a'
        self.__delimiter = schema.get_config_char_sequence(u'Delimiter') or u' '
        self.__combo_keys = schema.get_config_char_sequence(u'ComboKeys') or u''
        self.__combo_codes = schema.get_config_char_sequence(u'ComboCodes') or u''
        self.__combo_max_length = min(len(self.__combo_keys), len(self.__combo_codes))
        self.__combo_space = schema.get_config_value(u'ComboSpace') or u'_'
        get_rules = lambda f, key: [f(r.split()) for r in schema.get_config_list(key)]
        compile_repl_pattern = lambda x: (re.compile(x[0]), x[1])
        self.__xform_rules = get_rules(compile_repl_pattern, u'TransformRule')
        self.__combo = set()
        self.__held = set()
    def clear(self):
        self.__combo.clear()
        self.__held.clear()
    def __is_empty(self):
        return not bool(self.__held)
    def __get_prompt(self, first):
        text = self.__prompt_pattern % self.__get_combo_string()
        padding = None if first or self.__auto_predict else self.__delimiter[0]
        return Prompt(text, padding=padding)
    def __commit_combo(self, first):
        k = self.__get_combo_string()
        self.clear()
        #print '__commit_combo', k
        if k == self.__combo_space:
            return KeyEvent(keysyms.space, 0, coined=True)
        elif not k:
            return Prompt()
        else:
            return [k] if first else [self.__delimiter[0], k]
    def __get_combo_string(self):
        s = u''.join([self.__combo_codes[i] for i in range(self.__combo_max_length) \
                                                 if self.__combo_keys[i] in self.__combo])
        xform = lambda s, r: r[0].sub(r[1], s)
        return reduce(xform, self.__xform_rules, s)
    def process_input(self, event, ctx):
        # handle combo input
        ch = event.get_char()
        if event.mask & modifier.RELEASE_MASK:
            if ch in self.__held:
                #print 'released:', ch
                self.__held.remove(ch)
                if self.__is_empty():
                    return self.__commit_combo(ctx.is_empty())
                return True
            return False
        if ch in self.__combo_keys:
            #print 'pressed:', ch
            self.__combo.add(ch)
            self.__held.add(ch)
            return self.__get_prompt(ctx.is_empty())
        # non-combo keys
        if not self.__is_empty():
            self.clear()
            return Prompt()
        return False

def register_parsers():
    Parser.register('roman', RomanParser)
    Parser.register('grouping', GroupingParser)
    Parser.register('combo', ComboParser)
