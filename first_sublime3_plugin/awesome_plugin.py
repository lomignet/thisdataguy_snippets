# please always use shlex with subprocess
import shlex
import sublime
import sublime_plugin
import os


class UpdateOnSave(sublime_plugin.EventListener):

    def on_post_save_async(self, view):
        filename = view.file_name()
        savedfile = os.path.basename(filename)
        saveddir = os.path.dirname(filename)

        # write in sublime status buffer
        sublime.status_message('Manually saving ' + filename)

        source_in_vagrant = '/vagrant/' + savedfile
        dest_in_vagrant = '/project/' + savedfile

        cmd_cp = "vagrant ssh -c 'sudo cp {0} {1}'".format(source, dest)

        view.window().run_command('exec', {
            'cmd': shlex.split(cmd_cp),
            'working_dir': saveddir,
        }
        )