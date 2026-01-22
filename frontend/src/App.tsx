import React from "react";
import Container from "@mui/material/Container";
import Box from "@mui/material/Box";
import OverviewPage from "./pages/OverviewPage";

const App: React.FC = () => (
  <Container maxWidth="xl">
    <Box my={3}>
      <OverviewPage />
    </Box>
  </Container>
);

export default App;
