<script setup lang="ts">
// Foto do produto por arquivo: escolhe, padroniza (ajuste determinístico do
// servidor, degradável) e guarda no storage, devolvendo a URL a quem usa. O
// mesmo gesto serve à criação e à edição; quem grava o produto é o painel.
const props = defineProps<{
  enhance: (image: string) => Promise<string>;
  upload: (image: string) => Promise<string>;
  testid?: string;
}>();

const emit = defineEmits<{ stored: [url: string] }>();

const photoBusy = ref(false);
const photoError = ref("");
const photoOriginal = ref("");
const photoResult = ref("");
const uploadBusy = ref(false);
const storedUrl = ref("");

async function onPhotoPicked(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  photoResult.value = "";
  photoOriginal.value = "";
  storedUrl.value = "";
  photoError.value = "";
  if (file.size > 8 * 1024 * 1024) {
    photoError.value = "A foto é grande demais (máximo 8 MB).";
    return;
  }
  photoOriginal.value = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("read_failed"));
    reader.readAsDataURL(file);
  });
  photoBusy.value = true;
  try {
    photoResult.value = await props.enhance(photoOriginal.value);
  } catch (error) {
    // O ajuste é conveniência: sem ele a foto original ainda pode ser usada.
    photoError.value = httpErrorMessage(
      error,
      "Não foi possível padronizar a foto. A original ainda pode ser usada.",
    );
  } finally {
    photoBusy.value = false;
  }
}

async function usePhoto() {
  const image = photoResult.value || photoOriginal.value;
  if (!image) return;
  photoError.value = "";
  uploadBusy.value = true;
  try {
    storedUrl.value = await props.upload(image);
    emit("stored", storedUrl.value);
  } catch (error) {
    photoError.value = httpErrorMessage(
      error,
      "Não foi possível guardar a foto agora. A tela segue sem ela.",
    );
  } finally {
    uploadBusy.value = false;
  }
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <NuxtFormField
      label="Foto do produto"
      hint="Escolha uma imagem para padronizar."
    >
      <NuxtInput
        type="file"
        accept="image/*"
        :disabled="photoBusy"
        :data-testid="testid ? `${testid}-input` : undefined"
        @change="onPhotoPicked"
      />
    </NuxtFormField>
    <p class="text-xs text-muted-foreground">
      O ajuste é determinístico: recorta a borda, enquadra e afina. Não inventa
      o produto.
    </p>
    <p v-if="photoError" class="text-xs text-warning">
      {{ photoError }}
    </p>
    <div v-if="photoResult || photoOriginal" class="flex items-center gap-3">
      <img
        :src="photoResult || photoOriginal"
        alt="Prévia da foto"
        class="h-20 w-20 rounded object-cover"
      />
      <div class="flex flex-col items-start gap-1">
        <NuxtButton
          color="neutral"
          variant="outline"
          :label="storedUrl ? 'Foto guardada' : 'Usar como foto do produto'"
          :loading="uploadBusy"
          :disabled="Boolean(storedUrl) || photoBusy"
          :data-testid="testid ? `${testid}-use` : undefined"
          @click="usePhoto"
        />
        <a
          v-if="photoResult"
          :href="photoResult"
          download="produto.jpg"
          class="text-xs underline"
          >Baixar padronizada</a
        >
      </div>
    </div>
  </div>
</template>
