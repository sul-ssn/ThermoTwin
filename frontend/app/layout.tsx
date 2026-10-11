import "./globals.css";
import "maplibre-gl/dist/maplibre-gl.css";
export const metadata = {
  title: "ThermoTwin — цифровой двойник теплосети",
  description: "Моделирование аварий и поддержка диспетчерских решений",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
