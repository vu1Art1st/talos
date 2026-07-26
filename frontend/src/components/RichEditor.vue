<template>
  <div class="border border-gray-300 rounded-md bg-white">
    <div v-if="editor" class="flex flex-wrap gap-1 border-b border-gray-200 p-1.5">
      <el-button-group size="small">
        <el-button :type="editor.isActive('heading', { level: 2 }) ? 'primary' : ''"
                   @click="editor.chain().focus().toggleHeading({ level: 2 }).run()">H2</el-button>
        <el-button :type="editor.isActive('heading', { level: 3 }) ? 'primary' : ''"
                   @click="editor.chain().focus().toggleHeading({ level: 3 }).run()">H3</el-button>
        <el-button :type="editor.isActive('bold') ? 'primary' : ''"
                   @click="editor.chain().focus().toggleBold().run()"><b>B</b></el-button>
        <el-button :type="editor.isActive('italic') ? 'primary' : ''"
                   @click="editor.chain().focus().toggleItalic().run()"><i>I</i></el-button>
        <el-button :type="editor.isActive('strike') ? 'primary' : ''"
                   @click="editor.chain().focus().toggleStrike().run()"><s>S</s></el-button>
        <el-button :type="editor.isActive('code') ? 'primary' : ''"
                   @click="editor.chain().focus().toggleCode().run()">代码</el-button>
      </el-button-group>
      <el-button-group size="small">
        <el-button :type="editor.isActive('bulletList') ? 'primary' : ''"
                   @click="editor.chain().focus().toggleBulletList().run()">• 列表</el-button>
        <el-button :type="editor.isActive('orderedList') ? 'primary' : ''"
                   @click="editor.chain().focus().toggleOrderedList().run()">1. 列表</el-button>
        <el-button :type="editor.isActive('codeBlock') ? 'primary' : ''"
                   @click="editor.chain().focus().toggleCodeBlock().run()">代码块</el-button>
        <el-button :type="editor.isActive('blockquote') ? 'primary' : ''"
                   @click="editor.chain().focus().toggleBlockquote().run()">引用</el-button>
      </el-button-group>
      <el-button-group size="small">
        <el-button @click="editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()">插入表格</el-button>
        <el-button :disabled="!editor.can().addRowAfter()" @click="editor.chain().focus().addRowAfter().run()">+行</el-button>
        <el-button :disabled="!editor.can().addColumnAfter()" @click="editor.chain().focus().addColumnAfter().run()">+列</el-button>
        <el-button :disabled="!editor.can().deleteTable()" @click="editor.chain().focus().deleteTable().run()">删表格</el-button>
      </el-button-group>
      <el-button size="small" @click="fileInput?.click()">
        <el-icon class="mr-1"><Picture /></el-icon>图片
      </el-button>
      <el-button-group size="small">
        <el-button :disabled="!editor.can().undo()" @click="editor.chain().focus().undo().run()">撤销</el-button>
        <el-button :disabled="!editor.can().redo()" @click="editor.chain().focus().redo().run()">重做</el-button>
      </el-button-group>
      <input ref="fileInput" type="file" accept="image/*" class="hidden" @change="onPickImage" />
    </div>
    <editor-content :editor="editor" class="rich-content" />
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { Editor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import Link from '@tiptap/extension-link'
import Table from '@tiptap/extension-table'
import TableRow from '@tiptap/extension-table-row'
import TableCell from '@tiptap/extension-table-cell'
import TableHeader from '@tiptap/extension-table-header'
import client from '../api/client'

const props = defineProps<{ modelValue: string; placeholder?: string }>()
const emit = defineEmits<{
  (e: 'update:modelValue', html: string): void
  (e: 'update:json', json: any): void
}>()

const fileInput = ref<HTMLInputElement>()

const editor = new Editor({
  extensions: [
    StarterKit,
    Image.configure({ inline: false }),
    Link.configure({ openOnClick: false }),
    Table.configure({ resizable: true }),
    TableRow,
    TableHeader,
    TableCell,
  ],
  content: props.modelValue || '',
  onUpdate: ({ editor }) => {
    emit('update:modelValue', editor.getHTML())
    emit('update:json', editor.getJSON())
  },
  editorProps: {
    handlePaste(_view, event) {
      const items = event.clipboardData?.items
      if (!items) return false
      for (const item of items) {
        if (item.type.startsWith('image/')) {
          const file = item.getAsFile()
          if (file) uploadImage(file)
          return true
        }
      }
      return false
    },
  },
})

watch(
  () => props.modelValue,
  (val) => {
    if (val !== editor.getHTML()) editor.commands.setContent(val || '', false)
  },
)

async function uploadImage(file: File) {
  const form = new FormData()
  form.append('file', file)
  const { data } = await client.post('/upload/image', form)
  editor.chain().focus().setImage({ src: data.url }).run()
}

function onPickImage(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) uploadImage(file)
  ;(e.target as HTMLInputElement).value = ''
}

onBeforeUnmount(() => editor.destroy())
</script>
