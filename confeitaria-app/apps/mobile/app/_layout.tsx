import { Stack } from "expo-router";

export default function RootLayout() {
  return (
    <Stack screenOptions={{
      headerStyle: { backgroundColor: "#db2777" },
      headerTintColor: "#fff",
      headerTitleStyle: { fontWeight: "bold" },
    }}>
      <Stack.Screen name="index" options={{ title: "Confeitaria", headerShown: false }} />
      <Stack.Screen name="catalogo" options={{ title: "Catálogo" }} />
      <Stack.Screen name="agenda" options={{ title: "Agenda" }} />
      <Stack.Screen name="social" options={{ title: "Social" }} />
      <Stack.Screen name="carrinho" options={{ title: "Carrinho" }} />
    </Stack>
  );
}
