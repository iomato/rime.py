# -*- coding: utf-8 -*-
# vim:set et sts=4 sw=4:

import time
from core import *
from composer import *
from context import *

__all__ = (
    "Engine",
)


class Engine(Processor):

    ROLLBACK_COUNTDOWN = 3  # seconds

    def __init__(self, frontend, schema_id):
        self.__frontend = frontend
        self.schema = Schema(schema_id)
        self.__db = self.schema.get_db()
        self.__composer = Composer.create(self.schema)
        self.ctx = Context(self.schema)
        self.ctx.add_update_notifier(self)
        self.__auto_prompt = self.schema.get_config_value(u'AutoPrompt') in (u'yes', u'true')
        self.__punct = None
        self.__punct_key = 0
        self.__punct_rep = 0
        self.__rollback_time = 0
        self.__numeric = False
        self.update_ui()

    def process_key_event(self, event):
        # disable engine when Caps Lock is on
        if event.mask & modifier.LOCK_MASK:
            return False
        # ignore Num Lock
        event.mask &= ~modifier.MOD2_MASK
        # process hotkeys
        if event.mask & ( \
            modifier.CONTROL_MASK | modifier.ALT_MASK | \
            modifier.SUPER_MASK | modifier.HYPER_MASK | modifier.META_MASK
            ):
            if (event.mask & ~modifier.RELEASE_MASK) == modifier.CONTROL_MASK and \
                keycode >= keysyms._1 and keycode <= keysyms._9:
                candidates = self.ctx.get_candidates()
                if candidates:
                    if event.mask & modifier.RELEASE_MASK == 0:
                        # delete phrase
                        index = self.__frontend.get_candidate_index(event.keycode - keysyms._1)
                        if index >= 0 and index < len(candidates):
                            self.ctx.delete_phrase(candidates[index][1])
                    return True
            # ignore other hotkeys
            return False
        if self.__rollback_time:
            now = time.time()
            if now > self.__rollback_time:
                self.__db.proceed_pending_updates()
                self.__rollback_time = 0
        if self.__punct:
            if event.keycode in (keysyms.Shift_L, keysyms.Shift_R) or \
                (event.mask & modifier.RELEASE_MASK):
                return True
            if event.keycode == self.__punct_key:
                self.__next_punct()
                return True
            if event.keycode in (keysyms.Escape, keysyms.BackSpace):
                # clear punct prompt
                self.__commit_punct(commit=False)
                return True
            if event.keycode in(keysyms.space, keysyms.Return):
                self.__commit_punct()
                return True
            self.__commit_punct()
            # continue processing
        result = self.__composer.process_input(event, self.ctx)
        if result is True:
            return True
        if result is False:
            return self.__process(event)
        return self.__handle_parser_result(result)

    def __handle_parser_result(self, result):
        if isinstance(result, Commit):
            self.__frontend.commit_string(result)
            self.__composer.clear()
            self.ctx.clear()
            self.__numeric = False
            return True
        if isinstance(result, Spelling):
            if result.is_empty():
                self.update_ui()
            else:
                self.__update_spelling(result)
            return True    
        if isinstance(result, list):
            # handle input
            if self.__is_conversion_mode():
                if self.ctx.is_completed():
                    # auto-commit
                    self.__commit()
                else:
                    return True
            self.ctx.edit(self.ctx.input + result, start_conversion=self.__auto_prompt)
            return True
        if isinstance(result, KeyEvent):
            # coined key event
            return self.__process(result)
        # noop
        return True

    def __next_punct(self):
        self.__punct_rep = (self.__punct_rep + 1) % len(self.__punct)
        punct = self.__punct[self.__punct_rep]
        self.__frontend.update_preedit(punct, 0, len(punct))

    def __commit_punct(self, commit=True):
        punct = self.__punct[self.__punct_rep]
        self.__punct = None
        self.__punct_key = 0
        self.__punct_rep = 0
        self.__frontend.update_preedit(u'', 0, 0)
        if commit:
            self.__frontend.commit_string(punct)
            self.ctx.clear()
            self.__numeric = False

    def __judge(self, event):
        if event.mask & modifier.RELEASE_MASK == 0:
            self.update_ui()
            if self.__rollback_time and event.keycode == keysyms.BackSpace:
                self.__db.cancel_pending_updates()
                self.__rollback_time = 0
        if event.coined:
            if not event.mask:
                self.__frontend.commit_string(event.get_char())
            return True
        # 此標誌為判斷浮點數輸入而置
        if not (event.mask & modifier.RELEASE_MASK):
            self.__numeric = event.get_char().isdigit()
        return False

    def __process(self, event):
        ctx = self.ctx
        if ctx.is_empty():
            if event.mask & modifier.RELEASE_MASK and self.__punct:
                return True
            if self.__numeric and event.get_char() == u'.':
                return False
            if self.__handle_punct(event, commit=False):
                return True
            return self.__judge(event)
        if event.mask & modifier.RELEASE_MASK:
            return True
        edit_key = self.__composer.check_edit_key(event)
        if edit_key:
            return self.__process(edit_key)
        if event.keycode == keysyms.Escape:
            if self.__is_conversion_mode():
                ctx.cancel_conversion()
            elif ctx.has_error():
                ctx.pop_input(ctx.err.i)
                ctx.edit(ctx.input, start_conversion=self.__auto_prompt)
            else:
                ctx.edit([])
            return True
        if event.keycode == keysyms.BackSpace:
            if self.__is_conversion_mode(assumed=bool(event.mask & modifier.SHIFT_MASK)):
                ctx.back() or self.__auto_prompt or ctx.cancel_conversion()
            else:
                ctx.pop_input()
                ctx.edit(ctx.input, start_conversion=self.__auto_prompt)
            return True
        if event.keycode == keysyms.space:
            if ctx.being_converted():
                self.__confirm_current()
            else:
                ctx.edit(ctx.input, start_conversion=True)
            return True
        if event.keycode == keysyms.Return:
            if event.mask & modifier.SHIFT_MASK:
                self.__commit(as_display=True)
            elif self.__auto_prompt:
                self.__commit(plain_input=True)
            elif ctx.being_converted():
                self.__confirm_current()
            else:
                self.__commit()
            return True
        if event.keycode == keysyms.Tab:
            ctx.end(start_conversion=True)
            return True
        if event.keycode == keysyms.Home:
            ctx.home()
            return True
        if event.keycode == keysyms.End:
            ctx.end()
            return True
        if event.keycode == keysyms.Left:
            ctx.left()
            return True
        if event.keycode == keysyms.Right:
            ctx.right()
            return True
        candidates = ctx.get_candidates()
        if event.keycode == keysyms.Page_Up:
            if candidates and self.__frontend.page_up():
                self.__select_by_cursor(candidates)
                return True
            return True
        if event.keycode == keysyms.Page_Down:
            if candidates and self.__frontend.page_down():
                self.__select_by_cursor(candidates)
                return True
            return True
        if event.keycode == keysyms.Up:
            if candidates and self.__frontend.cursor_up():
                self.__select_by_cursor(candidates)
                return True
            return True
        if event.keycode == keysyms.Down:
            if candidates and self.__frontend.cursor_down():
                self.__select_by_cursor(candidates)
                return True
            return True
        if event.keycode >= keysyms._1 and event.keycode <= keysyms._9:
            if self.__select_by_index(candidates, event.keycode - keysyms._1):
                return True
            else:
                # auto-commit
                self.__commit()
                return self.__judge(event)
        # auto-commit
        if self.__handle_punct(event, commit=True):
            return True
        return True

    def __is_conversion_mode(self, assumed=False):
        return(not self.__auto_prompt or assumed) and self.ctx.being_converted()

    def __handle_punct(self, event, commit):
        result, punct = self.__composer.check_punct(event)
        if punct:
            if commit:
                self.__commit()
            if isinstance(punct, list):
                self.__punct = punct
                self.__punct_key = event.keycode
                self.__punct_rep = 0
                # prompt punct
                self.__frontend.update_preedit(punct[0], 0, len(punct[0]))
            else:
                self.__frontend.commit_string(punct)
                self.__numeric = False
        return result

    def __select_by_index(self, candidates, n):
        if not candidates:
            return False
        index = self.__frontend.get_candidate_index(n)
        if index >= 0 and index < len(candidates):
            self.ctx.select(candidates[index][1])
            self.__confirm_current()
        return True

    def __select_by_cursor(self, candidates):
        index = self.__frontend.get_highlighted_candidate_index()
        if index >= 0 and index < len(candidates):
            self.ctx.select(candidates[index][1])
            self.__frontend.update_preedit(self.ctx.get_prompt())
            sentence, start, end = self.ctx.get_sentence()
            self.__frontend.update_aux(sentence, start, end)
            return True
        return False

    def __confirm_current(self):
        if self.ctx.is_completed():
            self.__commit()
        else:
            self.ctx.forward()

    def __commit(self, as_display=False, plain_input=False):
        if plain_input:
            s = self.ctx.get_input_string() 
        elif as_display:
            s = self.ctx.get_display_string()
        else:
            s = self.ctx.get_commit_string()
        self.__frontend.commit_string(s)
        self.__composer.clear()
        self.ctx.commit()
        self.__rollback_time = time.time() + Engine.ROLLBACK_COUNTDOWN
        self.__numeric = False

    def __update_spelling(self, spelling):
        sentence, start, end = self.ctx.get_sentence()
        start = len(sentence) + spelling.start
        end = len(sentence) + spelling.end
        self.__frontend.update_aux(sentence + spelling.text, start, end)
        self.__frontend.update_preedit(self.ctx.get_prompt())
        self.__frontend.update_candidates([])

    # TODO:
    def update_ui(self):
        self.on_update(self.ctx)

    def on_update(self, ctx):
        self.__frontend.update_preedit(ctx.get_prompt())
        sentence, start, end = ctx.get_sentence()
        self.__frontend.update_aux(sentence, start, end)
        self.__frontend.update_candidates(ctx.get_candidates())
        

