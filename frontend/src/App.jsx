import { useEffect, useState } from "react";
import { getFurniture, createFurniture, deleteFurniture } from "./api";

export default function App() {
  const [items, setItems] = useState([]);

  const [form, setForm] = useState({
    name: "",
    category: "",
    location: "",
    price: "",
  });

  useEffect(() => {
    load();
  }, []);

  async function load() {
    const data = await getFurniture();
    setItems(data);
  }

  function handleChange(e) {
    setForm({ ...form, [e.target.name]: e.target.value });
  }

  async function handleSubmit(e) {
    e.preventDefault();

    await createFurniture({
      ...form,
      price: Number(form.price),
    });

    setForm({
      name: "",
      category: "",
      location: "",
      price: "",
    });

    load();
  }

  async function handleDelete(id) {
    await deleteFurniture(id);
    load();
  }

  return (
    <div className="min-h-screen bg-gray-50">
      
      {/* HEADER */}
      <header className="max-w-6xl mx-auto px-6 py-8 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-gray-800">
          Furniture Inventory
        </h1>
      </header>

      <main className="max-w-6xl mx-auto px-6">

        {/* FORM */}
        <div className="bg-white shadow-sm border rounded-2xl p-6 mb-8">
          <h2 className="text-lg font-semibold mb-4">
            Add new furniture
          </h2>

          <form
            onSubmit={handleSubmit}
            className="grid grid-cols-1 md:grid-cols-4 gap-4"
          >
            <input
              name="name"
              placeholder="Name"
              value={form.name}
              onChange={handleChange}
              className="border rounded-xl px-4 py-2 focus:outline-none focus:ring-2 focus:ring-black"
            />

            <input
              name="category"
              placeholder="Category"
              value={form.category}
              onChange={handleChange}
              className="border rounded-xl px-4 py-2 focus:outline-none focus:ring-2 focus:ring-black"
            />

            <input
              name="location"
              placeholder="Location"
              value={form.location}
              onChange={handleChange}
              className="border rounded-xl px-4 py-2 focus:outline-none focus:ring-2 focus:ring-black"
            />

            <input
              name="price"
              placeholder="Price"
              value={form.price}
              onChange={handleChange}
              className="border rounded-xl px-4 py-2 focus:outline-none focus:ring-2 focus:ring-black"
            />

            <button
              type="submit"
              className="md:col-span-4 bg-black text-white py-2 rounded-xl hover:bg-gray-800 transition"
            >
              Add Item
            </button>
          </form>
        </div>

        {/* GRID */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">

          {items.map((item) => (
            <div
              key={item.id}
              className="bg-white border rounded-2xl shadow-sm hover:shadow-md transition overflow-hidden"
            >

              {/* IMAGE PLACEHOLDER */}
              <div className="h-40 bg-gray-100 flex items-center justify-center text-gray-400">
                No Image
              </div>

              {/* CONTENT */}
              <div className="p-4">

                <h3 className="text-xl font-semibold text-gray-800">
                  {item.name}
                </h3>

                <p className="text-sm text-gray-500 mt-1">
                  {item.category}
                </p>

                <p className="text-sm text-gray-500">
                  {item.location}
                </p>

                <div className="flex items-center justify-between mt-4">

                  <span className="text-lg font-bold text-gray-900">
                    €{item.price}
                  </span>

                  <button
                    onClick={() => handleDelete(item.id)}
                    className="text-sm bg-red-500 text-white px-3 py-1 rounded-lg hover:bg-red-600 transition"
                  >
                    Delete
                  </button>

                </div>
              </div>
            </div>
          ))}

        </div>
      </main>
    </div>
  );
}