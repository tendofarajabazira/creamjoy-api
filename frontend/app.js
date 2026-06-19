const API_URL = "http://127.0.0.1:5000";
const token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdGFmZl9pZCI6MTEsIm5hbWUiOiJKYWNrIiwicm9sZSI6ImRlbGl2ZXJ5IiwiZXhwIjoxNzgxOTUwOTg4fQ.zB2VOjvJlvgV-jhaFoMtMPikngIeFPWMa89qcqXPVb8";

async function apiFetch(url, options = {}) {
  options.headers = {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${token}`,
    ...(options.headers || {})
  };
  return fetch(url, options);
}

function statusBadge(status) {
  const clean = status && status.trim() !== "" ? status.trim() : "pending";

  if (clean === "delivered") {
    return `<span style="background:#1D9E75;color:white;padding:6px 10px;border-radius:5px;font-weight:bold;display:inline-block;">delivered</span>`;
  }

  if (clean === "completed") {
    return `<span style="background:#1D9E75;color:white;padding:6px 10px;border-radius:5px;font-weight:bold;display:inline-block;">completed</span>`;
  }

  if (clean === "dispatched" || clean === "in_progress") {
    return `<span style="background:orange;color:white;padding:6px 10px;border-radius:5px;font-weight:bold;display:inline-block;">${clean}</span>`;
  }

  return `<span style="background:grey;color:white;padding:6px 10px;border-radius:5px;font-weight:bold;display:inline-block;">${clean}</span>`;
}

async function loadBatches() {
  const response = await apiFetch(`${API_URL}/api/batches`);
  const batches = await response.json();

  const tbody = document.getElementById("batchesTableBody");
  tbody.innerHTML = "";

  batches.forEach(batch => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${batch.batch_number}</td>
      <td>${batch.batch_date}</td>
      <td>Loaded from API</td>
      <td>${batch.total_units}</td>
      <td>${statusBadge(batch.status)}</td>
    `;
    tbody.appendChild(row);
  });
}

async function loadOrders() {
  const response = await apiFetch(`${API_URL}/api/orders`);
  const orders = await response.json();

  const tbody = document.getElementById("ordersTableBody");
  tbody.innerHTML = "";

  orders.forEach(order => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${order.customer_name}</td>
      <td>Products ordered</td>
      <td>${order.total_amount}</td>
      <td>${statusBadge(order.payment_status)}</td>
      <td><button onclick="changeOrderStatus(${order.order_id})">Change Status</button></td>
    `;
    tbody.appendChild(row);
  });
}

async function changeOrderStatus(orderId) {
  const response = await apiFetch(`${API_URL}/api/orders/${orderId}/status`, {
    method: "PUT",
    body: JSON.stringify({ status: "delivered" })
  });

  if (response.ok) {
    loadOrders();
  }
}

document.getElementById("showBatchFormBtn").addEventListener("click", () => {
  document.getElementById("batchForm").classList.toggle("hidden");
});

document.getElementById("batchForm").addEventListener("submit", async (event) => {
  event.preventDefault();

  const data = {
    batch_number: document.getElementById("batchNumber").value,
    date: document.getElementById("batchDate").value,
    products: [
      {
        product_id: 1,
        quantity: Number(document.getElementById("quantity").value)
      }
    ],
    staff_id: Number(document.getElementById("staffSelect").value)
  };

  const response = await apiFetch(`${API_URL}/api/batches`, {
    method: "POST",
    body: JSON.stringify(data)
  });

  if (response.ok) {
    document.getElementById("batchForm").reset();
    document.getElementById("batchForm").classList.add("hidden");
    loadBatches();
  } else {
    const error = await response.json();
    alert(error.error || "Failed to create batch");
  }
});

window.onload = () => {
  loadBatches();
  loadOrders();
};
